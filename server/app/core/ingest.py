"""Shared ingest pipeline used by both the native and OTLP endpoints.

Spans are upserted (keyed by trace + span id) so the SDK can stream a span at
start time and complete it later — that is what makes the live view live.
Trace aggregates are recomputed inside the same transaction.
"""

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import broker, project_channel
from app.core.pricing import estimate_cost
from app.core.timeutil import as_utc
from app.models import Project, Span, Trace
from app.schemas.ingest import SpanIn, TraceIn
from app.schemas.traces import SpanOut, TraceSummary

logger = logging.getLogger(__name__)


async def ingest_batch(
    db: AsyncSession,
    project: Project,
    traces_in: list[TraceIn],
    spans_in: list[SpanIn],
) -> tuple[int, int]:
    trace_meta: dict[str, TraceIn] = {t.trace_id: t for t in traces_in}
    spans_by_trace: dict[str, list[SpanIn]] = defaultdict(list)
    for span in spans_in:
        spans_by_trace[span.trace_id].append(span)

    all_trace_ids = set(trace_meta) | set(spans_by_trace)
    if not all_trace_ids:
        return 0, 0

    result = await db.execute(
        select(Trace).where(Trace.project_id == project.id, Trace.trace_id.in_(all_trace_ids))
    )
    traces: dict[str, Trace] = {t.trace_id: t for t in result.scalars()}

    accepted_spans = 0
    touched: list[Trace] = []
    touched_spans: list[tuple[Trace, Span]] = []

    for trace_id in all_trace_ids:
        meta = trace_meta.get(trace_id)
        batch = spans_by_trace.get(trace_id, [])
        trace = traces.get(trace_id)

        if trace is None:
            trace = _create_trace(project, trace_id, meta, batch)
            db.add(trace)
            await db.flush()  # assign PK before spans reference it
            traces[trace_id] = trace
        elif meta is not None:
            _apply_trace_meta(trace, meta)

        if batch:
            upserted = await _upsert_spans(db, project, trace, batch)
            accepted_spans += len(upserted)
            touched_spans.extend((trace, s) for s in upserted)

        await _recompute_aggregates(db, trace, explicit_status=meta.status if meta else None)
        touched.append(trace)

    await db.commit()

    # Publish only after the transaction lands, so live clients never see
    # state that later rolled back.
    for trace, span in touched_spans:
        _publish_span(project, trace, span)
    for trace in touched:
        _publish_trace(project, trace)
    return len(touched), accepted_spans


def _create_trace(
    project: Project, trace_id: str, meta: TraceIn | None, batch: list[SpanIn]
) -> Trace:
    root = next((s for s in batch if s.parent_span_id is None), None)
    started = None
    if meta and meta.started_at:
        started = meta.started_at
    elif batch:
        started = min(s.started_at for s in batch)
    name = (meta.name if meta else None) or (root.name if root else None)
    if not name:
        name = batch[0].name if batch else "trace"
    from app.models import utcnow

    trace = Trace(
        project_id=project.id,
        trace_id=trace_id,
        name=name,
        session_id=meta.session_id if meta else None,
        meta=meta.metadata if meta else None,
        started_at=as_utc(started) or utcnow(),
        status="running",
    )
    if meta and meta.ended_at:
        trace.ended_at = as_utc(meta.ended_at)
    return trace


def _apply_trace_meta(trace: Trace, meta: TraceIn) -> None:
    if meta.name:
        trace.name = meta.name
    if meta.session_id:
        trace.session_id = meta.session_id
    if meta.metadata is not None:
        trace.meta = meta.metadata
    if meta.started_at:
        trace.started_at = as_utc(meta.started_at)
    if meta.ended_at:
        trace.ended_at = as_utc(meta.ended_at)


async def _upsert_spans(
    db: AsyncSession, project: Project, trace: Trace, batch: list[SpanIn]
) -> list[Span]:
    result = await db.execute(select(Span).where(Span.trace_pk == trace.id))
    existing: dict[str, Span] = {s.span_id: s for s in result.scalars()}

    upserted: list[Span] = []
    for span_in in batch:
        span = existing.get(span_in.span_id)
        if span is None:
            span = Span(
                trace_pk=trace.id,
                project_id=project.id,
                span_id=span_in.span_id,
                started_at=as_utc(span_in.started_at),
                name=span_in.name,
            )
            db.add(span)
            existing[span_in.span_id] = span
        _merge_span(span, span_in)
        upserted.append(span)
    return upserted


def _merge_span(span: Span, data: SpanIn) -> None:
    """Newer non-null values win; a start event followed by an end event
    composes into one complete span."""
    span.name = data.name
    span.kind = data.kind
    span.status = data.status
    span.parent_span_id = data.parent_span_id
    span.started_at = as_utc(data.started_at)
    if data.ended_at is not None:
        span.ended_at = as_utc(data.ended_at)
    if data.input is not None:
        span.input = data.input
    if data.output is not None:
        span.output = data.output
    if data.attributes is not None:
        span.attributes = data.attributes
    if data.events is not None:
        span.events = data.events
    if data.model is not None:
        span.model = data.model
    if data.input_tokens is not None:
        span.input_tokens = data.input_tokens
    if data.output_tokens is not None:
        span.output_tokens = data.output_tokens
    if data.error is not None:
        span.error_type = data.error.type
        span.error_message = data.error.message
        span.error_stacktrace = data.error.stacktrace
    if data.cost_usd is not None:
        span.cost_usd = data.cost_usd
    elif span.cost_usd is None:
        span.cost_usd = estimate_cost(span.model, span.input_tokens, span.output_tokens)


async def _recompute_aggregates(
    db: AsyncSession, trace: Trace, explicit_status: str | None = None
) -> None:
    result = await db.execute(select(Span).where(Span.trace_pk == trace.id))
    spans = list(result.scalars())

    trace.span_count = len(spans)
    trace.error_count = sum(1 for s in spans if s.status == "error")
    trace.llm_call_count = sum(1 for s in spans if s.kind == "LLM")
    trace.input_tokens = sum(s.input_tokens or 0 for s in spans)
    trace.output_tokens = sum(s.output_tokens or 0 for s in spans)
    trace.cost_usd = round(sum(s.cost_usd or 0.0 for s in spans), 8)

    if spans:
        trace.started_at = min(as_utc(s.started_at) for s in spans)
        if all(s.ended_at is not None for s in spans):
            trace.ended_at = max(as_utc(s.ended_at) for s in spans)

    if explicit_status is not None:
        trace.status = explicit_status
        return
    if trace.error_count > 0:
        trace.status = "error"
    elif spans and all(s.status != "running" for s in spans) and trace.ended_at is not None:
        trace.status = "ok"
    else:
        trace.status = "running"


def _publish_trace(project: Project, trace: Trace) -> None:
    broker.publish(
        project_channel(str(project.id)),
        "trace.updated",
        {"trace": TraceSummary.model_validate(trace).model_dump(mode="json")},
    )


def _publish_span(project: Project, trace: Trace, span: Span) -> None:
    broker.publish(
        project_channel(str(project.id)),
        "span.upserted",
        {
            "trace_pk": str(trace.id),
            "trace_id": trace.trace_id,
            "span": SpanOut.model_validate(span).model_dump(mode="json"),
        },
    )
