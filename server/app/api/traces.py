import math
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_owned_project
from app.core.timeutil import as_utc
from app.db import get_db
from app.models import Project, Trace, User, utcnow
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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TraceListResponse:
    query = select(Trace).where(Trace.project_id == project.id)
    if status_filter in ("running", "ok", "error"):
        query = query.where(Trace.status == status_filter)
    if session_id:
        query = query.where(Trace.session_id == session_id)
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(Trace.name.ilike(pattern), Trace.trace_id.ilike(pattern)))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    result = await db.execute(
        query.order_by(Trace.started_at.desc()).limit(limit).offset(offset)
    )
    items = [TraceSummary.model_validate(t) for t in result.scalars()]
    return TraceListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/projects/{project_id}/stats", response_model=ProjectStats)
async def project_stats(
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
    hours: int = Query(default=24, ge=1, le=24 * 30),
) -> ProjectStats:
    cutoff = utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(Trace).where(Trace.project_id == project.id, Trace.started_at >= cutoff)
    )
    traces = list(result.scalars())

    durations = sorted(
        t.duration_ms
        for t in traces
        if as_utc(t.ended_at) is not None and t.duration_ms is not None
    )
    error_count = sum(1 for t in traces if t.status == "error")

    bucket_count = min(48, max(12, hours))
    bucket_width = timedelta(hours=hours) / bucket_count
    buckets: list[StatsBucket] = []
    for i in range(bucket_count):
        b_start = cutoff + i * bucket_width
        b_end = b_start + bucket_width
        in_bucket = [t for t in traces if b_start <= as_utc(t.started_at) < b_end]
        b_durations = [t.duration_ms for t in in_bucket if t.duration_ms is not None]
        buckets.append(
            StatsBucket(
                bucket_start=b_start,
                trace_count=len(in_bucket),
                error_count=sum(1 for t in in_bucket if t.status == "error"),
                avg_duration_ms=(sum(b_durations) / len(b_durations)) if b_durations else None,
                total_tokens=sum(t.input_tokens + t.output_tokens for t in in_bucket),
                cost_usd=round(sum(t.cost_usd for t in in_bucket), 6),
            )
        )

    p95 = None
    if durations:
        p95 = durations[min(len(durations) - 1, math.ceil(len(durations) * 0.95) - 1)]

    return ProjectStats(
        window_hours=hours,
        trace_count=len(traces),
        error_count=error_count,
        error_rate=(error_count / len(traces)) if traces else 0.0,
        avg_duration_ms=(sum(durations) / len(durations)) if durations else None,
        p95_duration_ms=p95,
        total_input_tokens=sum(t.input_tokens for t in traces),
        total_output_tokens=sum(t.output_tokens for t in traces),
        total_cost_usd=round(sum(t.cost_usd for t in traces), 6),
        buckets=buckets,
    )


async def get_owned_trace(
    trace_pk: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Trace:
    result = await db.execute(
        select(Trace)
        .options(selectinload(Trace.spans))
        .join(Project, Trace.project_id == Project.id)
        .where(Trace.id == trace_pk, Project.owner_id == user.id)
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    return trace


@router.get("/traces/{trace_pk}", response_model=TraceDetail)
async def get_trace(trace: Trace = Depends(get_owned_trace)) -> TraceDetail:
    spans = sorted(trace.spans, key=lambda s: as_utc(s.started_at))
    summary = TraceSummary.model_validate(trace)
    return TraceDetail(
        **summary.model_dump(), spans=[SpanOut.model_validate(s) for s in spans]
    )


@router.delete("/traces/{trace_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trace(
    trace: Trace = Depends(get_owned_trace), db: AsyncSession = Depends(get_db)
) -> None:
    await db.delete(trace)
    await db.commit()
