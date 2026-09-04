import asyncio
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_owned_project
from app.core.events import broker, project_channel
from app.models import Project

router = APIRouter(prefix="/api", tags=["live"])

HEARTBEAT_SECONDS = 15


@router.get("/projects/{project_id}/events")
async def stream_project_events(
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

    async def event_stream():
        queue = broker.subscribe(channel)
        sent = 0
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if trace_id is not None:
                    event_trace_id = payload.get("trace_id") or payload.get("trace", {}).get(
                        "trace_id"
                    )
                    if event_trace_id != trace_id:
                        continue
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
