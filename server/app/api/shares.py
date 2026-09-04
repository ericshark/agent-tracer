import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.security import generate_share_token
from app.core.timeutil import as_utc
from app.db import get_db
from app.models import Project, ShareLink, Trace, User, utcnow
from app.schemas.share import PublicTraceOut, ShareCreate, ShareOut
from app.schemas.traces import SpanOut, TraceSummary

router = APIRouter(prefix="/api", tags=["share"])


async def _load_owned_trace(db: AsyncSession, user: User, trace_pk: uuid.UUID) -> Trace:
    result = await db.execute(
        select(Trace)
        .join(Project, Trace.project_id == Project.id)
        .where(Trace.id == trace_pk, Project.owner_id == user.id)
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    return trace


@router.post(
    "/traces/{trace_pk}/shares",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    trace_pk: uuid.UUID,
    payload: ShareCreate | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareOut:
    """Create a secure, read-only share link for a trace.

    The body is optional; omitting it creates a link that never expires.
    """
    expires_in_hours = payload.expires_in_hours if payload else None
    trace = await _load_owned_trace(db, user, trace_pk)
    share = ShareLink(
        trace_pk=trace.id,
        created_by=user.id,
        token=generate_share_token(),
        expires_at=(
            utcnow() + timedelta(hours=expires_in_hours) if expires_in_hours else None
        ),
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return ShareOut.model_validate(share)


@router.get("/traces/{trace_pk}/shares", response_model=list[ShareOut])
async def list_shares(
    trace_pk: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ShareOut]:
    trace = await _load_owned_trace(db, user, trace_pk)
    result = await db.execute(
        select(ShareLink).where(ShareLink.trace_pk == trace.id).order_by(ShareLink.created_at)
    )
    return [ShareOut.model_validate(s) for s in result.scalars()]


@router.delete("/shares/{share_id}", response_model=ShareOut)
async def revoke_share(
    share_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareOut:
    result = await db.execute(
        select(ShareLink)
        .join(Trace, ShareLink.trace_pk == Trace.id)
        .join(Project, Trace.project_id == Project.id)
        .where(ShareLink.id == share_id, Project.owner_id == user.id)
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if share.revoked_at is None:
        share.revoked_at = utcnow()
        await db.commit()
        await db.refresh(share)
    return ShareOut.model_validate(share)


@router.get("/share/{token}", response_model=PublicTraceOut)
async def view_shared_trace(token: str, db: AsyncSession = Depends(get_db)) -> PublicTraceOut:
    """Public, unauthenticated read-only view behind an unguessable token."""
    result = await db.execute(select(ShareLink).where(ShareLink.token == token))
    share = result.scalar_one_or_none()
    if share is None or share.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    expires = as_utc(share.expires_at)
    if expires is not None and expires <= utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link has expired")

    result = await db.execute(
        select(Trace).options(selectinload(Trace.spans)).where(Trace.id == share.trace_pk)
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    project = await db.get(Project, trace.project_id)
    spans = sorted(trace.spans, key=lambda s: as_utc(s.started_at))
    return PublicTraceOut(
        trace=TraceSummary.model_validate(trace),
        spans=[SpanOut.model_validate(s) for s in spans],
        project_name=project.name if project else "",
    )
