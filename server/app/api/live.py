import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import SESSION_COOKIE, get_owned_project
from app.core.events import broker, project_channel
from app.core.security import hash_api_key
from app.db import get_session_factory
from app.models import BrowserSession, Project, utcnow

router = APIRouter(prefix="/api", tags=["live"])

HEARTBEAT_SECONDS = 15


@router.get("/projects/{project_id}/events")
async def stream_project_events(
    request: Request,
    project: Project = Depends(get_owned_project),
    trace_id: str | None = Query(default=None, pattern="^[0-9a-f]{32}$"),
    limit: int | None = Query(default=None, ge=1, le=1000),
) -> StreamingResponse:
    """Server-Sent Events stream of live trace/span activity for a project.

    - `trace_id` filters the stream to a single trace.
    - `limit` closes the stream after N data events (useful for scripts/tests);
      without it the stream stays open until the client disconnects.
    """
    channel = project_channel(str(project.id))
    token_hash = hash_api_key(request.cookies[SESSION_COOKIE])

    async def session_is_active() -> bool:
        async with get_session_factory()() as db:
            return bool(
                await db.scalar(
                    select(BrowserSession.token_hash)
                    .join(Project, Project.owner_id == BrowserSession.user_id)
                    .where(
                        BrowserSession.token_hash == token_hash,
                        BrowserSession.expires_at > utcnow(),
                        Project.id == project.id,
                    )
                )
            )

    async def event_stream():
        queue = broker.subscribe(channel)
        sent = 0
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    if not await session_is_active():
                        return
                    yield ": heartbeat\n\n"
                    continue
                if trace_id is not None:
                    event_trace_id = payload.get("trace_id") or payload.get("trace", {}).get(
                        "trace_id"
                    )
                    if event_trace_id != trace_id:
                        continue
                if not await session_is_active():
                    return
                yield broker.format_sse(payload)
                sent += 1
                if limit is not None and sent >= limit:
                    return
        finally:
            # Runs on client disconnect (generator cancellation) as well.
            broker.unsubscribe(channel, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
