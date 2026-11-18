import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import can_access, load_trace
from app.api.deps import get_current_user
from app.core.security import generate_share_token
from app.core.timeutil import as_utc
from app.db import get_db
from app.models import Project, ShareLink, Trace, User, utcnow
from app.schemas.share import PublicTraceOut, ShareCreate, ShareLookup, ShareOut

router = APIRouter(prefix="/api", tags=["share"])


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
    expires_in_hours = (payload or ShareCreate()).expires_in_hours
    trace = await load_trace(db, user, trace_pk, with_spans=False)
    share = ShareLink(
        trace_pk=trace.id,
        created_by=user.id,
        token=generate_share_token(),
        expires_at=utcnow() + timedelta(hours=expires_in_hours),
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
    trace = await load_trace(db, user, trace_pk, with_spans=False)
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
        .where(ShareLink.id == share_id, can_access(user))
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    if share.revoked_at is None:
        share.revoked_at = utcnow()
        await db.commit()
        await db.refresh(share)
    return ShareOut.model_validate(share)


def public_projection(trace: Trace) -> PublicTraceOut:
    return PublicTraceOut(
        duration_ms=trace.duration_ms,
        span_count=trace.span_count,
        error_count=trace.error_count,
        llm_call_count=trace.llm_call_count,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
    )


@router.get("/traces/{trace_pk}/share-preview", response_model=PublicTraceOut)
async def preview_share(
    trace_pk: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PublicTraceOut:
    return public_projection(await load_trace(db, user, trace_pk, with_spans=False))


@router.post("/share", response_model=PublicTraceOut)
async def lookup_share(
    payload: ShareLookup, response: Response, db: AsyncSession = Depends(get_db)
) -> PublicTraceOut:
    return await view_shared_trace(payload.token, response, db)


@router.get("/share/{token}", response_model=PublicTraceOut)
async def view_shared_trace(
    token: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> PublicTraceOut:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    share = await db.scalar(select(ShareLink).where(ShareLink.token == token))
    if share is None or share.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found")
    expires = as_utc(share.expires_at)
    if expires is None or expires <= utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link has expired")
    trace = await db.get(Trace, share.trace_pk)
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    return public_projection(trace)
