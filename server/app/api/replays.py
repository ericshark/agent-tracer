import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.replay import ReplayError, execute_replay
from app.db import get_db
from app.models import Project, Replay, Span, User
from app.schemas.replay import ReplayCreate, ReplayOut

router = APIRouter(prefix="/api", tags=["replay"])


async def get_owned_span(
    span_pk: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Span:
    result = await db.execute(
        select(Span)
        .join(Project, Span.project_id == Project.id)
        .where(Span.id == span_pk, Project.owner_id == user.id)
    )
    span = result.scalar_one_or_none()
    if span is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Span not found")
    return span


@router.post(
    "/spans/{span_pk}/replays",
    response_model=ReplayOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_replay(
    payload: ReplayCreate,
    span: Span = Depends(get_owned_span),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReplayOut:
    """Safely re-run an LLM span. Executes a single model call with the
    recorded (or edited) input; never touches tools or the original trace."""
    try:
        replay = await execute_replay(db, user, span, payload)
    except ReplayError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ReplayOut.model_validate(replay)


@router.get("/spans/{span_pk}/replays", response_model=list[ReplayOut])
async def list_replays(
    span: Span = Depends(get_owned_span), db: AsyncSession = Depends(get_db)
) -> list[ReplayOut]:
    result = await db.execute(
        select(Replay).where(Replay.span_pk == span.id).order_by(Replay.created_at.desc())
    )
    return [ReplayOut.model_validate(r) for r in result.scalars()]
