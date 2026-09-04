"""In-process pub/sub broker powering the live SSE streams.

Single-process design: uvicorn runs one worker in the default deployment, so a
simple asyncio fan-out is sufficient. Scaling out would swap this for Redis
pub/sub behind the same interface.
"""

import asyncio
import json
from collections import defaultdict
from typing import Any


class EventBroker:
    def __init__(self, max_queue_size: int = 500) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._max_queue_size = max_queue_size

    def subscribe(self, channel: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers[channel].add(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        self._subscribers[channel].discard(queue)
        if not self._subscribers[channel]:
            self._subscribers.pop(channel, None)

    def publish(self, channel: str, event_type: str, data: dict[str, Any]) -> None:
        payload = {"type": event_type, **data}
        for queue in list(self._subscribers.get(channel, ())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer: drop the event rather than block ingest.
                pass

    @staticmethod
    def format_sse(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, default=str)}\n\n"


broker = EventBroker()


def project_channel(project_id: str) -> str:
    return f"project:{project_id}"
