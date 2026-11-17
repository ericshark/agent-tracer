"""Authorization for project-scoped resources.

Every route resolves traces, spans and other project children through here,
so the rule for "may this user see this project?" lives in exactly one place.
"""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import ColumnElement

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Project, Span, Trace, User


def can_access(user: User) -> ColumnElement[bool]:
    """SQL predicate over Project rows the user may access."""
    return Project.owner_id == user.id


async def load_trace(
    db: AsyncSession, user: User, trace_pk: uuid.UUID, *, with_spans: bool = True
) -> Trace:
    query = (
        select(Trace)
        .join(Project, Trace.project_id == Project.id)
        .where(Trace.id == trace_pk, can_access(user))
    )
    if with_spans:
        query = query.options(selectinload(Trace.spans))
    trace = (await db.execute(query)).scalar_one_or_none()
    if trace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    return trace


async def load_span(db: AsyncSession, user: User, span_pk: uuid.UUID) -> Span:
    result = await db.execute(
        select(Span)
        .join(Project, Span.project_id == Project.id)
        .where(Span.id == span_pk, can_access(user))
    )
    span = result.scalar_one_or_none()
    if span is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Span not found")
    return span


async def get_owned_trace(
    trace_pk: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Trace:
    return await load_trace(db, user, trace_pk)


async def get_owned_span(
    span_pk: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Span:
    return await load_span(db, user, span_pk)
