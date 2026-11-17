"""Experiments: run a target over a dataset, score every result, compare runs."""

import asyncio
import hashlib
import json
import logging
import math
import random
import re
import secrets
import time
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.evals.base import EvalContext, EvalResult, SpanView, as_text
from app.core.evals.registry import run_evaluator
from app.core.events import broker, project_channel
from app.core.ingest import ingest_batch
from app.core.jobs import job_handler
from app.core.llm import (
    Credentials,
    LLMRequest,
    complete,
    infer_provider,
    load_credentials,
    parse_llm_input,
)
from app.core.pricing import estimate_cost
from app.core.scores import upsert_score
from app.core.timeutil import as_utc
from app.models import (
    Evaluator,
    Experiment,
    ExperimentItem,
    Project,
    Span,
    Trace,
    utcnow,
)
from app.schemas.ingest import SpanErrorIn, SpanIn, TraceIn
from app.schemas.scores import ScoreBase

logger = logging.getLogger(__name__)

EXPERIMENT_ENVIRONMENT = "experiment"
JOB_KIND = "experiment.run"

# ------------------------------------------------------------------- templates

_VAR = re.compile(r"\{\{\s*input((?:\.[A-Za-z0-9_\-]+)*)\s*\}\}")


def _lookup(value: Any, path: str) -> Any:
    for part in [p for p in path.split(".") if p]:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return ""
    return value


def render(template: str, item_input: Any) -> str:
    """Substitute `{{input}}` and `{{input.field.sub}}` in a prompt template."""

    def replace(match: re.Match) -> str:
        value = _lookup(item_input, match.group(1))
        return value if isinstance(value, str) else as_text(value)

    return _VAR.sub(replace, template)


def build_messages(target: dict[str, Any], item_input: Any) -> tuple[list[dict], str | None]:
    system = target.get("system")
    template = target.get("messages")
    if template:
        messages = [
            {**m, "content": render(m["content"], item_input)}
            if isinstance(m.get("content"), str)
            else m
            for m in template
        ]
        return messages, render(system, item_input) if system else None
    try:
        # No template: the test case is itself a recorded model call.
        return parse_llm_input(item_input, system)
    except ValueError:
        return [{"role": "user", "content": as_text(item_input)}], system


# --------------------------------------------------------------------- context


def span_views(spans: list[Span]) -> list[SpanView]:
    ordered = sorted(spans, key=lambda s: (as_utc(s.started_at), s.span_id))
    return [
        SpanView(
            name=s.name,
            kind=s.kind,
            status=s.status,
            input=s.input,
            output=s.output,
            duration_ms=s.duration_ms,
        )
        for s in ordered
    ]


def context_for_trace(trace: Trace, span: Span | None = None, expected: Any = None) -> EvalContext:
    """Evaluation context for a recorded trace (or one span within it)."""
    spans = list(trace.spans)
    if span is None:
        roots = [s for s in spans if s.parent_span_id is None] or spans
        focus = min(roots, key=lambda s: as_utc(s.started_at), default=None)
        return EvalContext(
            input=focus.input if focus else None,
            output=focus.output if focus else None,
            expected=expected,
            spans=span_views(spans),
            latency_ms=trace.duration_ms,
            cost_usd=trace.cost_usd,
            total_tokens=trace.input_tokens + trace.output_tokens,
        )
    tokens = (span.input_tokens or 0) + (span.output_tokens or 0)
    return EvalContext(
        input=span.input,
        output=span.output,
        expected=expected,
        spans=span_views(spans),
        latency_ms=span.duration_ms,
        cost_usd=span.cost_usd,
        total_tokens=tokens or None,
    )


async def _context_for_item(db: AsyncSession, item: ExperimentItem) -> EvalContext:
    spans: list[SpanView] = []
    trace: Trace | None = None
    if item.trace_pk is not None:
        result = await db.execute(
            select(Trace).options(selectinload(Trace.spans)).where(Trace.id == item.trace_pk)
        )
        trace = result.scalar_one_or_none()
        if trace is not None:
            spans = span_views(list(trace.spans))
    tokens = (item.input_tokens or 0) + (item.output_tokens or 0)
    if not tokens and trace is not None:
        tokens = trace.input_tokens + trace.output_tokens
    return EvalContext(
        input=item.input,
        output=item.output,
        expected=item.expected_output,
        spans=spans,
        latency_ms=item.latency_ms
        if item.latency_ms is not None
        else getattr(trace, "duration_ms", None),
        cost_usd=item.cost_usd if item.cost_usd is not None else getattr(trace, "cost_usd", None),
        total_tokens=tokens or None,
    )


def score_entry(result: EvalResult, source: str) -> dict[str, Any]:
    return {
        "value": result.value,
        "data_type": result.data_type,
        "comment": result.comment,
        "source": source,
    }


# ------------------------------------------------------------------- execution


async def _call_target(
    target: dict[str, Any], item_input: Any, creds: Credentials
) -> dict[str, Any]:
    """One model call for one test case. Never raises: failures are results."""
    messages, system = build_messages(target, item_input)
    model = target["model"]
    provider = target.get("provider") or infer_provider(model, creds)
    started = utcnow()
    clock = time.perf_counter()
    out: dict[str, Any] = {
        "messages": messages,
        "system": system,
        "provider": provider,
        "started_at": started,
    }
    try:
        result = await complete(
            LLMRequest(
                provider=provider,
                model=model,
                messages=messages,
                system=system,
                max_tokens=int(target.get("max_tokens") or 4096),
            ),
            creds,
        )
        out.update(
            output=result.output,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
        )
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:4000]
    out["latency_ms"] = round((time.perf_counter() - clock) * 1000.0, 3)
    return out


async def _record_run(
    db: AsyncSession,
    project: Project,
    experiment: Experiment,
    item: ExperimentItem,
    run: dict[str, Any],
) -> None:
    """Store the result on the item and as an ordinary trace, so an experiment
    run can be opened in the waterfall like any other."""
    model = experiment.target["model"]
    failed = "error" in run
    simulated = run["provider"] == "simulation"
    cost = (
        None
        if simulated or failed
        else estimate_cost(
            model,
            run.get("input_tokens"),
            run.get("output_tokens"),
            run.get("cache_read_tokens"),
            run.get("cache_creation_tokens"),
        )
    )
    trace_id = secrets.token_hex(16)
    ended = run["started_at"] + timedelta(milliseconds=run["latency_ms"])
    llm_input: dict[str, Any] = {"messages": run["messages"]}
    if run["system"]:
        llm_input["system"] = run["system"]
    await ingest_batch(
        db,
        project,
        [
            TraceIn(
                trace_id=trace_id,
                name=experiment.name,
                environment=EXPERIMENT_ENVIRONMENT,
                metadata={
                    "experiment_id": str(experiment.id),
                    "dataset_item_id": str(item.dataset_item_id),
                },
                status="error" if failed else "ok",
            )
        ],
        [
            SpanIn(
                trace_id=trace_id,
                span_id=secrets.token_hex(8),
                name=model,
                kind="LLM",
                status="error" if failed else "ok",
                started_at=run["started_at"],
                ended_at=ended,
                input=llm_input,
                output=run.get("output"),
                model=model,
                input_tokens=run.get("input_tokens"),
                output_tokens=run.get("output_tokens"),
                cache_read_tokens=run.get("cache_read_tokens"),
                cache_creation_tokens=run.get("cache_creation_tokens"),
                # Simulated calls are free; don't let the price table bill them.
                cost_usd=0.0 if simulated else None,
                error=SpanErrorIn(type="ProviderError", message=run["error"]) if failed else None,
            )
        ],
    )
    trace_pk = (
        await db.execute(
            select(Trace.id).where(Trace.project_id == project.id, Trace.trace_id == trace_id)
        )
    ).scalar_one()
    item.trace_id = trace_id
    item.trace_pk = trace_pk
    item.output = run.get("output")
    item.status = "error" if failed else "ok"
    item.error = run.get("error")
    item.latency_ms = run["latency_ms"]
    item.input_tokens = run.get("input_tokens")
    item.output_tokens = run.get("output_tokens")
    item.cost_usd = 0.0 if simulated else cost


async def evaluate_item(
    db: AsyncSession,
    item: ExperimentItem,
    evaluators: list[Evaluator],
    creds: Credentials,
) -> None:
    scores = dict(item.scores or {})
    if item.status == "ok" and evaluators:
        ctx = await _context_for_item(db, item)
        for evaluator in evaluators:
            try:
                result = await run_evaluator(evaluator.template, evaluator.config, ctx, creds)
            except Exception as exc:  # provider failure: keep going, record why
                result = EvalResult(value=None, error=f"{type(exc).__name__}: {exc}"[:1000])
            if result.error is not None:
                scores[evaluator.name] = {
                    "value": None,
                    "data_type": result.data_type,
                    "comment": None,
                    "source": "evaluator",
                    "error": result.error,
                }
                continue
            scores[evaluator.name] = score_entry(result, "evaluator")
    item.scores = scores
    item.evaluated = True

    # Mirror onto the trace so the scores also show up in trace views.
    if item.trace_pk is not None:
        for name, entry in scores.items():
            if entry.get("value") is None:
                continue
            await upsert_score(
                db,
                project_id=item.project_id,
                trace_pk=item.trace_pk,
                span_pk=None,
                data=ScoreBase(
                    name=name,
                    value=entry["value"],
                    data_type=entry.get("data_type"),
                    comment=entry.get("comment"),
                    external_id=f"exp:{item.id}:{name}"[:255],
                ),
                source=entry.get("source") or "evaluator",
            )


# --------------------------------------------------------------------- summary


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    return None


def _percentile(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    return sorted_values[min(len(sorted_values) - 1, math.ceil(len(sorted_values) * p) - 1)]


def summarize(items: list[ExperimentItem]) -> dict[str, Any]:
    scores: dict[str, dict[str, Any]] = {}
    for item in items:
        for name, entry in (item.scores or {}).items():
            agg = scores.setdefault(
                name,
                {"data_type": entry.get("data_type"), "values": [], "labels": {}, "errors": 0},
            )
            if entry.get("error"):
                agg["errors"] += 1
                continue
            number = _numeric(entry.get("value"))
            if number is not None:
                agg["values"].append(number)
            elif entry.get("value") is not None:
                label = str(entry["value"])
                agg["labels"][label] = agg["labels"].get(label, 0) + 1
    latencies = sorted(i.latency_ms for i in items if i.latency_ms is not None)
    return {
        "item_count": len(items),
        "error_count": sum(1 for i in items if i.status == "error"),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "total_cost_usd": round(sum(i.cost_usd or 0.0 for i in items), 6),
        "total_tokens": sum((i.input_tokens or 0) + (i.output_tokens or 0) for i in items),
        "scores": {
            name: {
                "data_type": agg["data_type"],
                "count": len(agg["values"]) + sum(agg["labels"].values()),
                "mean": round(sum(agg["values"]) / len(agg["values"]), 4)
                if agg["values"]
                else None,
                "distribution": agg["labels"],
                "errors": agg["errors"],
            }
            for name, agg in sorted(scores.items())
        },
    }


async def item_progress(db: AsyncSession, experiment_ids: list[uuid.UUID]) -> dict:
    """experiment id → (total items, finished items)."""
    if not experiment_ids:
        return {}
    result = await db.execute(
        select(ExperimentItem.experiment_id, ExperimentItem.status, func.count())
        .where(ExperimentItem.experiment_id.in_(experiment_ids))
        .group_by(ExperimentItem.experiment_id, ExperimentItem.status)
    )
    progress: dict[uuid.UUID, list[int]] = {}
    for experiment_id, item_status, count in result.all():
        entry = progress.setdefault(experiment_id, [0, 0])
        entry[0] += count
        if item_status != "pending":
            entry[1] += count
    return {k: (v[0], v[1]) for k, v in progress.items()}


def _publish(experiment: Experiment, done: int, total: int) -> None:
    broker.publish(
        project_channel(str(experiment.project_id)),
        "experiment.updated",
        {
            "experiment_id": str(experiment.id),
            "status": experiment.status,
            "completed_count": done,
            "item_count": total,
        },
    )


# ------------------------------------------------------------------------- job


@job_handler(JOB_KIND)
async def run_experiment(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Execute (for prompt targets), evaluate and summarise an experiment.

    Safe to retry: finished items are skipped and scores are upserted.
    """
    experiment = await db.get(Experiment, uuid.UUID(payload["experiment_id"]))
    if experiment is None or experiment.status in ("completed", "failed"):
        return
    project = await db.get(Project, experiment.project_id)
    assert project is not None
    experiment.status = "running"
    await db.commit()

    creds = await load_credentials(db, project.id)
    evaluators: list[Evaluator] = []
    if experiment.evaluator_ids:
        ids = [uuid.UUID(str(e)) for e in experiment.evaluator_ids]
        result = await db.execute(
            select(Evaluator).where(Evaluator.project_id == project.id, Evaluator.id.in_(ids))
        )
        evaluators = sorted(result.scalars(), key=lambda e: e.name)

    result = await db.execute(
        select(ExperimentItem)
        .where(ExperimentItem.experiment_id == experiment.id)
        .order_by(ExperimentItem.created_at, ExperimentItem.id)
    )
    items = list(result.scalars())
    total = len(items)
    done = sum(1 for i in items if i.evaluated)

    try:
        target = experiment.target or {}
        if target.get("type") == "prompt":
            pending = [i for i in items if i.status == "pending"]
            width = max(1, get_settings().experiment_concurrency)
            for start in range(0, len(pending), width):
                chunk = pending[start : start + width]
                # Model calls run in parallel; database writes stay sequential.
                runs = await asyncio.gather(
                    *(_call_target(target, item.input, creds) for item in chunk)
                )
                for item, run in zip(chunk, runs, strict=True):
                    await _record_run(db, project, experiment, item, run)
                    await evaluate_item(db, item, evaluators, creds)
                    await db.commit()
                    done += 1
                    _publish(experiment, done, total)
        else:
            # Results were uploaded by the SDK; link their traces, then evaluate.
            for item in items:
                if item.evaluated:
                    continue
                if item.trace_pk is None and item.trace_id is not None:
                    item.trace_pk = (
                        await db.execute(
                            select(Trace.id).where(
                                Trace.project_id == project.id, Trace.trace_id == item.trace_id
                            )
                        )
                    ).scalar_one_or_none()
                await evaluate_item(db, item, evaluators, creds)
                await db.commit()
                done += 1
                _publish(experiment, done, total)
        # Items that needed no work still have to be marked evaluated.
        for item in items:
            if not item.evaluated:
                await evaluate_item(db, item, evaluators, creds)
        experiment.summary = summarize(items)
        experiment.status = "completed"
    except Exception as exc:
        logger.exception("Experiment %s failed", experiment.id)
        await db.rollback()
        experiment = await db.get(Experiment, experiment.id)
        assert experiment is not None
        experiment.status = "failed"
        experiment.error = f"{type(exc).__name__}: {exc}"[:4000]
    experiment.completed_at = utcnow()
    await db.commit()
    _publish(experiment, done, total)


# ------------------------------------------------------------------ comparison


def _item_key(item: ExperimentItem) -> str:
    if item.dataset_item_id is not None:
        return str(item.dataset_item_id)
    encoded = json.dumps(item.input, sort_keys=True, default=str)
    return "input:" + hashlib.sha256(encoded.encode()).hexdigest()[:24]


def _score_value(item: ExperimentItem | None, name: str) -> float | None:
    if item is None:
        return None
    return _numeric(((item.scores or {}).get(name) or {}).get("value"))


def _bootstrap_ci(diffs: list[float], rounds: int = 1000) -> tuple[float, float] | None:
    """95% bootstrap interval for the mean paired difference."""
    if len(diffs) < 2:
        return None
    rng = random.Random(1234)  # deterministic: same inputs, same interval
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(rounds))
    return round(means[int(rounds * 0.025)], 4), round(means[int(rounds * 0.975) - 1], 4)


def compare_experiments(
    experiments: list[Experiment], items_by_experiment: dict[uuid.UUID, list[ExperimentItem]]
) -> dict[str, Any]:
    """Align experiments by test case; the first experiment is the baseline."""
    base = experiments[0]
    keyed: dict[uuid.UUID, dict[str, ExperimentItem]] = {
        exp.id: {_item_key(i): i for i in items_by_experiment.get(exp.id, [])}
        for exp in experiments
    }
    order: list[str] = []
    for exp in experiments:
        for key in keyed[exp.id]:
            if key not in order:
                order.append(key)

    rows = []
    for key in order:
        first = next(keyed[exp.id][key] for exp in experiments if key in keyed[exp.id])
        cells = {}
        for exp in experiments:
            item = keyed[exp.id].get(key)
            if item is None:
                continue
            cells[str(exp.id)] = {
                "item_id": str(item.id),
                "output": item.output,
                "status": item.status,
                "error": item.error,
                "scores": item.scores or {},
                "latency_ms": item.latency_ms,
                "cost_usd": item.cost_usd,
                "trace_pk": str(item.trace_pk) if item.trace_pk else None,
            }
        rows.append(
            {
                "key": key,
                "input": first.input,
                "expected_output": first.expected_output,
                "cells": cells,
            }
        )

    names = sorted(
        {name for by_key in keyed.values() for i in by_key.values() for name in i.scores or {}}
    )
    scores: dict[str, list[dict[str, Any]]] = {}
    for name in names:
        per_experiment = []
        for exp in experiments:
            values = [
                v for item in keyed[exp.id].values() if (v := _score_value(item, name)) is not None
            ]
            entry: dict[str, Any] = {
                "experiment_id": str(exp.id),
                "mean": round(sum(values) / len(values), 4) if values else None,
                "count": len(values),
            }
            if exp.id != base.id:
                diffs = []
                for key, item in keyed[exp.id].items():
                    ours = _score_value(item, name)
                    theirs = _score_value(keyed[base.id].get(key), name)
                    if ours is not None and theirs is not None:
                        diffs.append(ours - theirs)
                ci = _bootstrap_ci(diffs)
                entry.update(
                    paired=len(diffs),
                    delta=round(sum(diffs) / len(diffs), 4) if diffs else None,
                    improved=sum(1 for d in diffs if d > 1e-9),
                    regressed=sum(1 for d in diffs if d < -1e-9),
                    unchanged=sum(1 for d in diffs if abs(d) <= 1e-9),
                    ci_low=ci[0] if ci else None,
                    ci_high=ci[1] if ci else None,
                )
            per_experiment.append(entry)
        scores[name] = per_experiment
    return {"baseline_id": str(base.id), "scores": scores, "rows": rows}
