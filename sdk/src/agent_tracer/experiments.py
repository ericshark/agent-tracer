"""Run your own code over a dataset and score the results.

    result = tracer.experiment(
        "prompt-v2",
        dataset="billing-questions",
        task=lambda question: my_agent(question),
        evaluators=[exact_match],            # run locally, in this process
        server_evaluators=["correctness"],   # configured in the dashboard
    )
    print(result.scores)                     # {"exact_match": 0.9, "correctness": 0.84}

Each task call is traced like production code, so every result links to a
waterfall, and trajectory evaluators can inspect the tools your agent used.
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .datasets import Dataset, DatasetItem
from .serialize import safe_json

_UPLOAD_BATCH = 200


def evaluator(name_or_func: Any = None, *, name: str | None = None) -> Any:
    """Mark a function as a local evaluator and name the score it produces.

        @evaluator
        def exact_match(output, expected):
            return output == expected

    The function may accept any of `output`, `expected`, `input`, `metadata`
    and returns a number, a bool, a label, `(value, comment)`, or None to skip.
    """

    def decorate(func: Callable) -> Callable:
        func.score_name = name or getattr(func, "__name__", "score")  # type: ignore[attr-defined]
        return func

    if callable(name_or_func):
        return decorate(name_or_func)
    if isinstance(name_or_func, str):
        name = name_or_func
    return decorate


def _call_evaluator(func: Callable, item: DatasetItem, output: Any) -> dict[str, Any] | None:
    available = {
        "output": output,
        "expected": item.expected_output,
        "input": item.input,
        "metadata": item.metadata,
    }
    params = inspect.signature(func).parameters
    kwargs = {k: v for k, v in available.items() if k in params}
    result = func(**kwargs)
    if result is None:
        return None
    comment = None
    if isinstance(result, tuple) and len(result) == 2:
        result, comment = result
    score_name = getattr(func, "score_name", None) or getattr(func, "__name__", "score")
    return {"name": score_name, "value": result, "comment": comment}


def _git_metadata() -> dict[str, str]:
    """Best-effort commit and branch, so a result can be traced to the code."""

    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], capture_output=True, text=True, timeout=2, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() or None if out.returncode == 0 else None

    meta = {
        "git_sha": git("rev-parse", "--short", "HEAD"),
        "git_branch": git("branch", "--show-current"),
    }
    return {k: v for k, v in meta.items() if v}


@dataclass
class ItemResult:
    input: Any
    expected_output: Any
    output: Any
    error: str | None
    trace_id: str | None
    latency_ms: float
    scores: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExperimentResult:
    id: str
    name: str
    status: str
    url: str
    #: score name → mean (numbers and pass rates); None until evaluation finishes
    scores: dict[str, float | None] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    items: list[ItemResult] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if item.error)


def _as_items(tracer: Any, dataset: Any) -> tuple[str | None, list[DatasetItem]]:
    if isinstance(dataset, str):
        fetched = tracer.datasets.get(dataset)
        return fetched.name, fetched.items
    if isinstance(dataset, Dataset):
        return dataset.name, dataset.items
    items = []
    for raw in dataset:
        if isinstance(raw, DatasetItem):
            items.append(raw)
        elif isinstance(raw, dict) and "input" in raw:
            items.append(
                DatasetItem(
                    id="",
                    input=raw["input"],
                    expected_output=raw.get("expected_output"),
                    metadata=raw.get("metadata"),
                )
            )
        else:
            raise ValueError("Inline dataset items must be dicts with an 'input' key")
    return None, items


def run_experiment(
    tracer: Any,
    name: str,
    *,
    dataset: str | Dataset | Iterable[Any],
    task: Callable[[Any], Any],
    evaluators: Iterable[Callable] = (),
    server_evaluators: Iterable[str] = (),
    concurrency: int = 4,
    metadata: dict[str, Any] | None = None,
    description: str | None = None,
    wait: bool = True,
    timeout: float = 600.0,
) -> ExperimentResult:
    dataset_name, items = _as_items(tracer, dataset)
    if not items:
        raise ValueError("The dataset has no items")
    local = list(evaluators)
    api = tracer._api

    created = api.post(
        "/v1/experiments",
        {
            "name": name,
            "description": description,
            "dataset": dataset_name,
            "evaluators": list(server_evaluators),
            "metadata": {**_git_metadata(), **(metadata or {})} or None,
        },
    )
    experiment_id = created["id"]

    def run_one(item: DatasetItem) -> ItemResult:
        started = time.monotonic()
        output: Any = None
        error: str | None = None
        trace_id: str | None = None
        try:
            with tracer.trace(
                name,
                environment="experiment",
                metadata={"experiment_id": experiment_id, "dataset_item_id": item.id or None},
            ) as trace:
                trace_id = trace.trace_id
                with tracer.span("task", kind="CHAIN", input=item.input) as span:
                    output = task(item.input)
                    if inspect.isawaitable(output):
                        output = asyncio.run(output)  # type: ignore[arg-type]
                    span.set_output(output)
        except Exception as exc:  # a failing case is a result, not a crash
            error = f"{type(exc).__name__}: {exc}"[:8000]
        result = ItemResult(
            input=item.input,
            expected_output=item.expected_output,
            output=safe_json(output),
            error=error,
            trace_id=trace_id,
            latency_ms=round((time.monotonic() - started) * 1000.0, 3),
        )
        if error is None:
            for func in local:
                try:
                    score = _call_evaluator(func, item, output)
                except Exception as exc:
                    score = None
                    label = getattr(func, "score_name", getattr(func, "__name__", "evaluator"))
                    tracer_logger().warning("agent-tracer: evaluator %s failed: %s", label, exc)
                if score is not None:
                    result.scores.append(score)
        return result

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        results = list(pool.map(run_one, items))

    # Traces must be on the server before trajectory evaluators look for them.
    tracer.flush()
    payload = [
        {
            "dataset_item_id": item.id or None,
            "input": safe_json(result.input),
            "expected_output": safe_json(result.expected_output),
            "output": result.output,
            "error": result.error,
            "trace_id": result.trace_id,
            "latency_ms": result.latency_ms,
            "scores": [{k: v for k, v in s.items() if v is not None} for s in result.scores],
        }
        for item, result in zip(items, results)
    ]
    for start in range(0, len(payload), _UPLOAD_BATCH):
        api.post(
            f"/v1/experiments/{experiment_id}/items",
            {"items": payload[start : start + _UPLOAD_BATCH]},
        )
    state = api.post(f"/v1/experiments/{experiment_id}/complete", {})

    deadline = time.monotonic() + timeout
    while wait and state["status"] not in ("completed", "failed"):
        if time.monotonic() >= deadline:
            break
        time.sleep(1.0)
        state = api.get(f"/v1/experiments/{experiment_id}")

    summary = state.get("summary") or {}
    return ExperimentResult(
        id=experiment_id,
        name=name,
        status=state["status"],
        url=f"{api.base_url}/api/experiments/{experiment_id}",
        scores={k: v.get("mean") for k, v in (summary.get("scores") or {}).items()},
        summary=summary,
        items=results,
    )


def tracer_logger() -> Any:
    import logging

    return logging.getLogger("agent_tracer")
