"""Score persistence shared by the dashboard API, the SDK API and evaluators."""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import broker, project_channel
from app.models import Score, Trace
from app.schemas.scores import ScoreBase, ScoreOut

# Experiment runs are real traces, but they are test traffic: keep them (and the
# scores on them) out of production views unless explicitly asked for.
NOT_EXPERIMENT = or_(Trace.environment.is_(None), Trace.environment != "experiment")


def _split_value(data_type: str, value: Any) -> tuple[float | None, str | None]:
    if data_type == "categorical":
        return None, str(value)
    if data_type == "boolean":
        return (1.0 if bool(value) else 0.0), None
    return float(value), None


async def upsert_score(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    trace_pk: uuid.UUID,
    span_pk: uuid.UUID | None,
    data: ScoreBase,
    source: str,
    author_id: uuid.UUID | None = None,
) -> Score:
    """Insert a score, or update the existing one with the same `external_id`.

    Adds to the caller's transaction; the caller commits, then calls
    `publish_score` so live clients never see uncommitted state.
    """
    score: Score | None = None
    if data.external_id is not None:
        result = await db.execute(
            select(Score).where(
                Score.project_id == project_id, Score.external_id == data.external_id
            )
        )
        score = result.scalar_one_or_none()
    if score is None:
        score = Score(project_id=project_id, external_id=data.external_id)
        db.add(score)
    score.trace_pk = trace_pk
    score.span_pk = span_pk
    score.name = data.name
    score.data_type = data.data_type or "numeric"
    score.value, score.string_value = _split_value(score.data_type, data.value)
    score.comment = data.comment
    score.meta = data.metadata
    score.source = source
    score.author_id = author_id
    return score


def publish_score(score: Score) -> None:
    broker.publish(
        project_channel(str(score.project_id)),
        "score.created",
        {
            "trace_pk": str(score.trace_pk),
            "score": ScoreOut.model_validate(score).model_dump(mode="json"),
        },
    )


async def trace_score_briefs(
    db: AsyncSession, trace_pks: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, float | str]]:
    """Per trace: score name → mean value (or latest label for categorical)."""
    if not trace_pks:
        return {}
    result = await db.execute(
        select(Score.trace_pk, Score.name, Score.value, Score.string_value)
        .where(Score.trace_pk.in_(trace_pks))
        .order_by(Score.created_at)
    )
    sums: dict[tuple[uuid.UUID, str], list[float]] = {}
    out: dict[uuid.UUID, dict[str, float | str]] = {}
    for trace_pk, name, value, string_value in result.all():
        if value is not None:
            sums.setdefault((trace_pk, name), []).append(value)
        elif string_value is not None:
            out.setdefault(trace_pk, {})[name] = string_value
    for (trace_pk, name), values in sums.items():
        out.setdefault(trace_pk, {})[name] = round(sum(values) / len(values), 4)
    return out
