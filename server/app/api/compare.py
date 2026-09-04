import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.diffing import diff_traces
from app.db import get_db
from app.models import Project, Trace, User
from app.schemas.traces import TraceSummary

router = APIRouter(prefix="/api", tags=["compare"])


async def _load_owned_trace(db: AsyncSession, user: User, trace_pk: uuid.UUID) -> Trace:
    result = await db.execute(
        select(Trace)
        .options(selectinload(Trace.spans))
        .join(Project, Trace.project_id == Project.id)
        .where(Trace.id == trace_pk, Project.owner_id == user.id)
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trace {trace_pk} not found")
    return trace


@router.get("/compare")
async def compare_traces(
    base: uuid.UUID = Query(...),
    other: uuid.UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Align two traces span-by-span and report what changed between them."""
    base_trace = await _load_owned_trace(db, user, base)
    other_trace = await _load_owned_trace(db, user, other)
    diff = diff_traces(list(base_trace.spans), list(other_trace.spans))
    return {
        "base": TraceSummary.model_validate(base_trace).model_dump(mode="json"),
        "other": TraceSummary.model_validate(other_trace).model_dump(mode="json"),
        **diff,
    }
