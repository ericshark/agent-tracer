import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import get_session_factory
from app.models import Trace, utcnow

logger = logging.getLogger(__name__)


async def expire_traces(now: datetime | None = None) -> int:
    now = now or utcnow()
    enabled_at = get_settings().trace_retention_enabled_at
    cutoff = now - timedelta(days=30)
    if enabled_at is None or enabled_at > cutoff:
        return 0

    deleted = 0
    async with get_session_factory()() as db:
        while True:
            batch = (
                select(Trace.id)
                .where(Trace.started_at < cutoff)
                .order_by(Trace.started_at, Trace.id)
                .limit(250)
                .with_for_update(skip_locked=True)
            )
            result = await db.execute(delete(Trace).where(Trace.id.in_(batch)))
            await db.commit()
            deleted += result.rowcount
            if result.rowcount < 250:
                return deleted
            await asyncio.sleep(0)


async def retention_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            count = await expire_traces()
            if count:
                logger.info("Trace retention removed %d expired traces", count)
        except Exception:
            logger.error("Trace retention cleanup failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=86400)
        except TimeoutError:
            pass
