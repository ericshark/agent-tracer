import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import load_trace
from app.api.deps import get_current_user
from app.core.diffing import diff_traces
from app.db import get_db
from app.models import User
from app.schemas.traces import TraceSummary

router = APIRouter(prefix="/api", tags=["compare"])


@router.get("/compare")
async def compare_traces(
    base: uuid.UUID = Query(...),
    other: uuid.UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Align two traces span-by-span and report what changed between them."""
    base_trace = await load_trace(db, user, base)
    other_trace = await load_trace(db, user, other)
    diff = diff_traces(list(base_trace.spans), list(other_trace.spans))
    return {
        "base": TraceSummary.model_validate(base_trace).model_dump(mode="json"),
        "other": TraceSummary.model_validate(other_trace).model_dump(mode="json"),
        **diff,
    }
