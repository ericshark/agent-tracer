import math
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import get_owned_trace
from app.api.deps import get_owned_project
from app.core.scores import trace_score_briefs
from app.core.timeutil import as_utc
from app.db import get_db
from app.models import Project, Score, Trace, utcnow
from app.schemas.traces import (
    ProjectStats,
    SpanOut,
    StatsBucket,
    TraceDetail,
    TraceListResponse,
    TraceSummary,
)

router = APIRouter(prefix="/api", tags=["traces"])


@router.get("/projects/{project_id}/traces", response_model=TraceListResponse)
async def list_traces(
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=255),
    session_id: str | None = Query(default=None, max_length=255),
    user_id: str | None = Query(default=None, max_length=255),
    environment: str | None = Query(default=None, max_length=64),
    before: datetime | None = Query(default=None),
    score_name: str | None = Query(default=None, max_length=120),
    score_min: float | None = Query(default=None),
    score_max: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TraceListResponse:
    query = select(Trace).where(Trace.project_id == project.id)
    if status_filter in ("running", "ok", "error"):
        query = query.where(Trace.status == status_filter)
    if session_id:
        query = query.where(Trace.session_id == session_id)
    if user_id:
        query = query.where(Trace.user_id == user_id)
    if environment:
        query = query.where(Trace.environment == environment)
    if score_name:
        # Traces with at least one matching score in the requested range.
        scored = select(Score.trace_pk).where(
            Score.project_id == project.id, Score.name == score_name
        )
        if score_min is not None:
            scored = scored.where(Score.value >= score_min)
        if score_max is not None:
            scored = scored.where(Score.value <= score_max)
        query = query.where(Trace.id.in_(scored))
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(Trace.name.ilike(pattern), Trace.trace_id.ilike(pattern)))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    if before is not None:
        # Keyset pagination: cheaper than a deep OFFSET on large projects.
        query = query.where(Trace.started_at < before)
    result = await db.execute(
        query.order_by(Trace.started_at.desc(), Trace.id).limit(limit).offset(offset)
    )
    items = [TraceSummary.model_validate(t) for t in result.scalars()]
    briefs = await trace_score_briefs(db, [t.id for t in items])
    for item in items:
        item.scores = briefs.get(item.id)
    next_cursor = items[-1].started_at if len(items) == limit else None
    return TraceListResponse(
        items=items, total=total, limit=limit, offset=offset, next_cursor=next_cursor
    )


@router.get("/projects/{project_id}/stats", response_model=ProjectStats)
async def project_stats(
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
    hours: int = Query(default=24, ge=1, le=24 * 30),
) -> ProjectStats:
    cutoff = utcnow() - timedelta(hours=hours)
    # Plain column tuples, not ORM objects: a 30-day window can be large.
    rows = (
        await db.execute(
            select(
                Trace.started_at,
                Trace.ended_at,
                Trace.status,
                Trace.input_tokens,
                Trace.output_tokens,
                Trace.cost_usd,
            ).where(Trace.project_id == project.id, Trace.started_at >= cutoff)
        )
    ).all()

    bucket_count = min(48, max(12, hours))
    bucket_width = timedelta(hours=hours) / bucket_count
    acc = [
        {"n": 0, "errors": 0, "dur": 0.0, "dur_n": 0, "tokens": 0, "cost": 0.0}
        for _ in range(bucket_count)
    ]
    durations: list[float] = []
    error_count = 0
    total_in = total_out = 0
    total_cost = 0.0
    for started_at, ended_at, trace_status, in_tokens, out_tokens, cost in rows:
        started = as_utc(started_at)
        ended = as_utc(ended_at)
        duration = (ended - started).total_seconds() * 1000.0 if ended else None
        index = min(bucket_count - 1, max(0, int((started - cutoff) / bucket_width)))
        bucket = acc[index]
        bucket["n"] += 1
        bucket["tokens"] += in_tokens + out_tokens
        bucket["cost"] += cost
        if trace_status == "error":
            bucket["errors"] += 1
            error_count += 1
        if duration is not None:
            bucket["dur"] += duration
            bucket["dur_n"] += 1
            durations.append(duration)
        total_in += in_tokens
        total_out += out_tokens
        total_cost += cost

    durations.sort()
    p95 = None
    if durations:
        p95 = durations[min(len(durations) - 1, math.ceil(len(durations) * 0.95) - 1)]

    return ProjectStats(
        window_hours=hours,
        trace_count=len(rows),
        error_count=error_count,
        error_rate=(error_count / len(rows)) if rows else 0.0,
        avg_duration_ms=(sum(durations) / len(durations)) if durations else None,
        p95_duration_ms=p95,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=round(total_cost, 6),
        buckets=[
            StatsBucket(
                bucket_start=cutoff + i * bucket_width,
                trace_count=b["n"],
                error_count=b["errors"],
                avg_duration_ms=(b["dur"] / b["dur_n"]) if b["dur_n"] else None,
                total_tokens=b["tokens"],
                cost_usd=round(b["cost"], 6),
            )
            for i, b in enumerate(acc)
        ],
    )


@router.get("/traces/{trace_pk}", response_model=TraceDetail)
async def get_trace(
    trace: Trace = Depends(get_owned_trace), db: AsyncSession = Depends(get_db)
) -> TraceDetail:
    spans = sorted(trace.spans, key=lambda s: as_utc(s.started_at))
    summary = TraceSummary.model_validate(trace)
    summary.scores = (await trace_score_briefs(db, [trace.id])).get(trace.id)
    return TraceDetail(
        **summary.model_dump(), spans=[SpanOut.model_validate(s) for s in spans]
    )


@router.delete("/traces/{trace_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trace(
    trace: Trace = Depends(get_owned_trace), db: AsyncSession = Depends(get_db)
) -> None:
    await db.delete(trace)
    await db.commit()
