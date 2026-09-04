import time
import uuid
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decode_access_token, hash_api_key
from app.db import get_db
from app.models import ApiKey, Project, User, utcnow


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str | None = Query(default=None, include_in_schema=False),
) -> User:
    """Resolve the authenticated user from a Bearer header (or, for SSE
    clients that cannot set headers, a ?token= query parameter)."""
    raw = _extract_bearer(request) or token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_access_token(raw)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


async def get_owned_project(
    project_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    project = await db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def get_ingest_project(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Authenticate an ingest request via project API key.

    Accepts `Authorization: Bearer at_…` or `X-API-Key: at_…`.
    """
    key = _extract_bearer(request) or request.headers.get("X-API-Key")
    if not key or not key.startswith("at_"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API key")
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(key)))
    api_key = result.scalar_one_or_none()
    if api_key is None or api_key.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    api_key.last_used_at = utcnow()
    project = await db.get(Project, api_key.project_id)
    if project is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return project


class RateLimiter:
    """Small in-memory sliding-window limiter for the auth endpoints."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


auth_rate_limiter = RateLimiter()


async def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    ok = auth_rate_limiter.check(
        f"auth:{client_ip}",
        settings.auth_rate_limit_attempts,
        settings.auth_rate_limit_window_seconds,
    )
    if not ok:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, please retry later"
        )
