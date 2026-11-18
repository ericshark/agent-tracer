import time
import uuid
from collections import defaultdict, deque
from ipaddress import ip_address

from fastapi import Depends, HTTPException, Path, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_api_key
from app.db import get_db
from app.models import ApiKey, BrowserSession, Project, User, utcnow


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return None


SESSION_COOKIE = "at_session"
SESSION_SECONDS = 8 * 60 * 60


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = await db.scalar(
        select(User).join(BrowserSession).where(
            BrowserSession.token_hash == hash_api_key(token),
            BrowserSession.expires_at > utcnow(),
        )
    )
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
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


def require_api_key(scope: str):
    """Dependency factory: authenticate a project API key that carries `scope`.

    Accepts `Authorization: Bearer at_…` or `X-API-Key: at_…`.
    """

    async def dependency(request: Request, db: AsyncSession = Depends(get_db)) -> Project:
        key = _extract_bearer(request) or request.headers.get("X-API-Key")
        if not key or not key.startswith("at_"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API key")
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(key)))
        api_key = result.scalar_one_or_none()
        if api_key is None or api_key.revoked_at is not None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        if not api_key.has_scope(scope):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"API key is missing the '{scope}' scope"
            )
        api_key.last_used_at = utcnow()
        project = await db.get(Project, api_key.project_id)
        if project is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        settings = get_settings()
        if not ingest_rate_limiter.check(
            f"{scope}:{project.id}",
            settings.ingest_rate_limit_batches,
            settings.ingest_rate_limit_window_seconds,
        ):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "API rate limit exceeded")
        return project

    return dependency


get_ingest_project = require_api_key("ingest")
get_read_project = require_api_key("read")
get_write_project = require_api_key("write")


class RateLimiter:
    """Small in-memory sliding-window limiter for auth and ingestion."""

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
ingest_rate_limiter = RateLimiter()


async def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    # Configure this only behind an ingress that overwrites the named header.
    if settings.auth_client_ip_header:
        forwarded = request.headers.get(settings.auth_client_ip_header)
        if forwarded:
            try:
                client_ip = str(ip_address(forwarded))
            except ValueError:
                pass
    ok = auth_rate_limiter.check(
        f"auth:{client_ip}",
        settings.auth_rate_limit_attempts,
        settings.auth_rate_limit_window_seconds,
    )
    if not ok:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, please retry later"
        )
