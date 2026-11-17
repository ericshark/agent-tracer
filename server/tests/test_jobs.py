from app.core import jobs
from app.core.jobs import drain_jobs, enqueue, job_handler
from app.db import get_session_factory
from app.models import Job
from sqlalchemy import select


async def _enqueue(kind, payload, **kwargs):
    async with get_session_factory()() as db:
        job = await enqueue(db, kind, payload, **kwargs)
        await db.commit()
        return job


async def _jobs():
    async with get_session_factory()() as db:
        return list((await db.execute(select(Job))).scalars())


async def test_job_runs_and_completes(engine):
    seen = []

    @job_handler("test.ok")
    async def handle(db, payload):
        seen.append(payload["n"])

    await _enqueue("test.ok", {"n": 1})
    await _enqueue("test.ok", {"n": 2})
    assert await drain_jobs() == 2
    assert sorted(seen) == [1, 2]
    assert {j.status for j in await _jobs()} == {"done"}


async def test_dedupe_key_makes_enqueue_idempotent(engine):
    @job_handler("test.dedupe")
    async def handle(db, payload):
        pass

    assert await _enqueue("test.dedupe", {}, dedupe_key="k1") is not None
    assert await _enqueue("test.dedupe", {}, dedupe_key="k1") is None
    assert len(await _jobs()) == 1


async def test_failed_job_retries_then_fails(engine, monkeypatch):
    calls = []

    @job_handler("test.boom")
    async def handle(db, payload):
        calls.append(1)
        raise RuntimeError("boom")

    await _enqueue("test.boom", {}, max_attempts=2)
    assert await drain_jobs() == 1
    (job,) = await _jobs()
    assert job.status == "queued" and job.attempts == 1 and "boom" in job.error

    # Backoff pushed run_after into the future; make it due again.
    async with get_session_factory()() as db:
        row = await db.get(Job, job.id)
        row.run_after = jobs.utcnow()
        await db.commit()
    assert await drain_jobs() == 1
    (job,) = await _jobs()
    assert job.status == "failed" and len(calls) == 2


async def test_unknown_kind_fails_without_retry(engine):
    await _enqueue("test.nope", {})
    await drain_jobs()
    (job,) = await _jobs()
    assert job.status == "failed" and "No handler" in job.error
