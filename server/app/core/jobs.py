"""DB-backed background jobs.

No broker to operate: jobs are rows, claimed with `FOR UPDATE SKIP LOCKED` on
PostgreSQL (SQLite, used for tests and local hacking, is single-writer so a
plain claim is safe). The worker runs inside the API process by default
(`WORKER_MODE=inline`) or as a separate process (`python -m app.worker`).

Handlers are registered with `@job_handler("kind")` and receive a fresh
session plus the job payload. They must be idempotent: a job is retried with
backoff until `max_attempts`, and a crashed worker's job is re-queued.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory
from app.models import Job, utcnow

logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]
_HANDLERS: dict[str, Handler] = {}
_wakeup: asyncio.Event | None = None

STALE_LOCK = timedelta(minutes=15)
POLL_SECONDS = 5.0


def job_handler(kind: str) -> Callable[[Handler], Handler]:
    def register(func: Handler) -> Handler:
        _HANDLERS[kind] = func
        return func

    return register


async def enqueue(
    db: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    project_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> Job | None:
    """Add a job to the caller's transaction (the caller commits).

    Returns None when a job with the same `dedupe_key` already exists.
    """
    if dedupe_key is not None:
        existing = await db.execute(select(Job.id).where(Job.dedupe_key == dedupe_key))
        if existing.first() is not None:
            return None
    job = Job(
        kind=kind,
        payload=payload,
        project_id=project_id,
        dedupe_key=dedupe_key,
        run_after=run_after or utcnow(),
        max_attempts=max_attempts,
    )
    db.add(job)
    return job


def notify() -> None:
    """Nudge the in-process worker after a commit that enqueued work."""
    if _wakeup is not None:
        _wakeup.set()


async def _claim_next() -> uuid.UUID | None:
    async with get_session_factory()() as db:
        result = await db.execute(
            select(Job)
            .where(Job.status == "queued", Job.run_after <= utcnow())
            .order_by(Job.run_after, Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.locked_at = utcnow()
        await db.commit()
        return job.id


async def _run(job_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        kind, payload = job.kind, dict(job.payload or {})
        attempts, max_attempts = job.attempts, job.max_attempts

    error: str | None = None
    handler = _HANDLERS.get(kind)
    if handler is None:
        error, attempts = f"No handler registered for job kind {kind!r}", max_attempts
    else:
        try:
            async with factory() as db:
                await handler(db, payload)
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job_id, kind)
            error = f"{type(exc).__name__}: {exc}"[:4000]

    async with factory() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.locked_at = None
        if error is None:
            job.status, job.error, job.finished_at = "done", None, utcnow()
        elif attempts < max_attempts:
            job.status, job.error = "queued", error
            job.run_after = utcnow() + timedelta(seconds=min(300, 5 * 2**attempts))
        else:
            job.status, job.error, job.finished_at = "failed", error, utcnow()
        await db.commit()


async def run_one() -> bool:
    job_id = await _claim_next()
    if job_id is None:
        return False
    await _run(job_id)
    return True


async def drain_jobs(max_jobs: int = 10_000) -> int:
    """Run every job that is due right now. Used by tests and one-shot scripts."""
    ran = 0
    while ran < max_jobs and await run_one():
        ran += 1
    return ran


async def requeue_stale() -> None:
    """Recover jobs whose worker died mid-run."""
    async with get_session_factory()() as db:
        await db.execute(
            update(Job)
            .where(Job.status == "running", Job.locked_at < utcnow() - STALE_LOCK)
            .values(status="queued", locked_at=None)
        )
        await db.commit()


async def worker_loop(stop: asyncio.Event, concurrency: int = 2) -> None:
    global _wakeup
    _wakeup = asyncio.Event()
    logger.info("Job worker started (concurrency=%d)", concurrency)

    async def lane() -> None:
        while not stop.is_set():
            try:
                if await run_one():
                    continue
            except Exception:
                logger.exception("Job worker iteration failed")
            assert _wakeup is not None
            _wakeup.clear()
            try:
                await asyncio.wait_for(_wakeup.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass

    try:
        await requeue_stale()
    except Exception:
        logger.exception("Could not requeue stale jobs")
    try:
        await asyncio.gather(*(lane() for _ in range(concurrency)))
    finally:
        _wakeup = None
