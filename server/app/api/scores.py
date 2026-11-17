import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import can_access, load_trace
from app.api.deps import get_current_user, get_owned_project, get_write_project
from app.core.scores import NOT_EXPERIMENT, publish_score, upsert_score
from app.core.timeutil import as_utc
from app.db import get_db
from app.models import Project, Score, ScoreConfig, Span, Trace, User, utcnow
from app.schemas.scores import (
    ScoreConfigOut,
    ScoreConfigPut,
    ScoreCreate,
    ScoreIn,
    ScoreOut,
    ScoreSeriesPoint,
    ScoreSummary,
)

router = APIRouter(tags=["scores"])


# ------------------------------------------------------------- SDK-facing (/v1)


@router.post("/v1/scores", response_model=ScoreOut, status_code=status.HTTP_201_CREATED)
async def create_score_v1(
    payload: ScoreIn,
    project: Project = Depends(get_write_project),
    db: AsyncSession = Depends(get_db),
) -> ScoreOut:
    """Attach a score to an already-ingested trace (e.g. end-user feedback).

    Scores produced while a trace is running should ride along in the
    `/v1/ingest` batch instead, which is what the SDK does.
    """
    score = await score_from_wire_ids(db, project, payload, source="api")
    if score is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace or span not found")
    await db.commit()
    await db.refresh(score)
    publish_score(score)
    return ScoreOut.model_validate(score)


async def score_from_wire_ids(
    db: AsyncSession, project: Project, payload: ScoreIn, *, source: str
) -> Score | None:
    trace = (
        await db.execute(
            select(Trace).where(Trace.project_id == project.id, Trace.trace_id == payload.trace_id)
        )
    ).scalar_one_or_none()
    if trace is None:
        return None
    span_pk: uuid.UUID | None = None
    if payload.span_id is not None:
        span_pk = (
            await db.execute(
                select(Span.id).where(Span.trace_pk == trace.id, Span.span_id == payload.span_id)
            )
        ).scalar_one_or_none()
        if span_pk is None:
            return None
    return await upsert_score(
        db,
        project_id=project.id,
        trace_pk=trace.id,
        span_pk=span_pk,
        data=payload,
        source=source,
    )


# ------------------------------------------------------------------- dashboard


@router.get("/api/traces/{trace_pk}/scores", response_model=list[ScoreOut])
async def list_trace_scores(
    trace_pk: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScoreOut]:
    trace = await load_trace(db, user, trace_pk, with_spans=False)
    result = await db.execute(
        select(Score).where(Score.trace_pk == trace.id).order_by(Score.created_at.desc())
    )
    return [ScoreOut.model_validate(s) for s in result.scalars()]


@router.post(
    "/api/traces/{trace_pk}/scores",
    response_model=ScoreOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_trace_score(
    trace_pk: uuid.UUID,
    payload: ScoreCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreOut:
    """Annotate a trace (or one of its spans) by hand."""
    trace = await load_trace(db, user, trace_pk, with_spans=False)
    if payload.span_pk is not None:
        span = await db.get(Span, payload.span_pk)
        if span is None or span.trace_pk != trace.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Span not found")
    score = await upsert_score(
        db,
        project_id=trace.project_id,
        trace_pk=trace.id,
        span_pk=payload.span_pk,
        data=payload,
        source="human",
        author_id=user.id,
    )
    await db.commit()
    await db.refresh(score)
    publish_score(score)
    return ScoreOut.model_validate(score)


@router.delete("/api/scores/{score_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_score(
    score_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Score)
        .join(Project, Score.project_id == Project.id)
        .where(Score.id == score_id, can_access(user))
    )
    score = result.scalar_one_or_none()
    if score is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Score not found")
    await db.delete(score)
    await db.commit()


@router.get("/api/projects/{project_id}/scores/summary", response_model=list[ScoreSummary])
async def score_summary(
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
    hours: int = Query(default=24 * 7, ge=1, le=24 * 90),
) -> list[ScoreSummary]:
    """Per score name: count, mean, range, label distribution and a time series."""
    cutoff = utcnow() - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(Score.name, Score.data_type, Score.value, Score.string_value, Score.created_at)
            .join(Trace, Score.trace_pk == Trace.id)
            .where(Score.project_id == project.id, Score.created_at >= cutoff, NOT_EXPERIMENT)
        )
    ).all()

    bucket_count = min(30, max(12, hours // 24 or 12))
    width = timedelta(hours=hours) / bucket_count
    by_name: dict[str, dict] = {}
    for name, data_type, value, string_value, created_at in rows:
        entry = by_name.setdefault(
            name,
            {
                "data_type": data_type,
                "values": [],
                "distribution": {},
                "buckets": [[0, 0.0, 0] for _ in range(bucket_count)],
            },
        )
        index = min(bucket_count - 1, max(0, int((as_utc(created_at) - cutoff) / width)))
        bucket = entry["buckets"][index]
        bucket[0] += 1
        if value is not None:
            entry["values"].append(value)
            bucket[1] += value
            bucket[2] += 1
        if data_type == "boolean" and value is not None:
            label = "true" if value >= 0.5 else "false"
            entry["distribution"][label] = entry["distribution"].get(label, 0) + 1
        elif string_value is not None:
            entry["distribution"][string_value] = entry["distribution"].get(string_value, 0) + 1

    summaries = []
    for name, entry in sorted(by_name.items()):
        values = entry["values"]
        summaries.append(
            ScoreSummary(
                name=name,
                data_type=entry["data_type"],
                count=sum(b[0] for b in entry["buckets"]),
                mean=round(sum(values) / len(values), 4) if values else None,
                min=min(values) if values else None,
                max=max(values) if values else None,
                distribution=entry["distribution"],
                series=[
                    ScoreSeriesPoint(
                        bucket_start=cutoff + i * width,
                        count=b[0],
                        mean=round(b[1] / b[2], 4) if b[2] else None,
                    )
                    for i, b in enumerate(entry["buckets"])
                ],
            )
        )
    return summaries


# --------------------------------------------------------------- score configs


@router.get("/api/projects/{project_id}/score-configs", response_model=list[ScoreConfigOut])
async def list_score_configs(
    project: Project = Depends(get_owned_project), db: AsyncSession = Depends(get_db)
) -> list[ScoreConfigOut]:
    result = await db.execute(
        select(ScoreConfig).where(ScoreConfig.project_id == project.id).order_by(ScoreConfig.name)
    )
    return [ScoreConfigOut.model_validate(c) for c in result.scalars()]


@router.put("/api/projects/{project_id}/score-configs", response_model=ScoreConfigOut)
async def put_score_config(
    payload: ScoreConfigPut,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> ScoreConfigOut:
    if payload.data_type == "categorical" and not payload.categories:
        raise HTTPException(422, "A categorical score needs categories")
    result = await db.execute(
        select(ScoreConfig).where(
            ScoreConfig.project_id == project.id, ScoreConfig.name == payload.name
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = ScoreConfig(project_id=project.id, name=payload.name)
        db.add(config)
    config.data_type = payload.data_type
    config.min_value = payload.min_value
    config.max_value = payload.max_value
    config.categories = payload.categories
    config.description = payload.description
    await db.commit()
    await db.refresh(config)
    return ScoreConfigOut.model_validate(config)


@router.delete(
    "/api/projects/{project_id}/score-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_score_config(
    config_id: uuid.UUID,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> None:
    config = await db.get(ScoreConfig, config_id)
    if config is None or config.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Score config not found")
    await db.delete(config)
    await db.commit()
