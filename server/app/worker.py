"""Standalone job worker:  python -m app.worker

Run this next to the API with WORKER_MODE=external when background work
(evaluations, experiments, alerts) should not share the API process.
"""

import asyncio
import signal

from app.config import get_settings
from app.core import handlers  # noqa: F401  (registers job handlers)
from app.core.jobs import worker_loop
from app.db import get_engine
from app.logging_config import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    task = asyncio.create_task(worker_loop(stop, settings.worker_concurrency))
    await stop.wait()
    from app.core.jobs import notify

    notify()
    await task
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
