"""Background batching exporter.

Spans are queued from application threads/tasks and shipped to the collector
by a single daemon thread, so instrumentation never blocks the host app.
"""

from __future__ import annotations

import atexit
import logging
import queue
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("agent_tracer")

_FLUSH_SENTINEL = object()


class BatchExporter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        flush_interval: float = 0.5,
        max_batch_size: int = 100,
        max_queue_size: int = 10_000,
        max_retries: int = 3,
        timeout: float = 10.0,
    ) -> None:
        self._endpoint = base_url.rstrip("/") + "/v1/ingest"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._flush_interval = flush_interval
        self._max_batch_size = max_batch_size
        self._max_retries = max_retries
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=max_queue_size)
        self._client = httpx.Client(timeout=timeout)
        self._stopped = threading.Event()
        self._flush_done = threading.Event()
        self._worker = threading.Thread(
            target=self._run, name="agent-tracer-exporter", daemon=True
        )
        self._worker.start()
        atexit.register(self.shutdown)

    # -------------------------------------------------------------- enqueue

    def enqueue_span(self, span_payload: dict[str, Any]) -> None:
        self._enqueue({"kind": "span", "data": span_payload})

    def enqueue_trace(self, trace_payload: dict[str, Any]) -> None:
        self._enqueue({"kind": "trace", "data": trace_payload})

    def _enqueue(self, item: dict[str, Any]) -> None:
        if self._stopped.is_set():
            return
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            logger.warning("agent-tracer: export queue full, dropping telemetry")

    # ---------------------------------------------------------------- flush

    def flush(self, timeout: float = 10.0) -> bool:
        """Block until everything queued so far has been exported."""
        if self._stopped.is_set():
            return True
        self._flush_done.clear()
        self._queue.put(_FLUSH_SENTINEL)
        return self._flush_done.wait(timeout)

    def shutdown(self, timeout: float = 10.0) -> None:
        if self._stopped.is_set():
            return
        self.flush(timeout)
        self._stopped.set()
        self._queue.put(_FLUSH_SENTINEL)  # wake the worker so it can exit
        self._worker.join(timeout=2.0)
        try:
            self._client.close()
        except Exception:
            pass

    # --------------------------------------------------------------- worker

    def _run(self) -> None:
        pending: list[dict[str, Any]] = []
        deadline = time.monotonic() + self._flush_interval
        while True:
            timeout = max(0.01, deadline - time.monotonic())
            flush_requested = False
            try:
                item = self._queue.get(timeout=timeout)
                if item is _FLUSH_SENTINEL:
                    flush_requested = True
                else:
                    pending.append(item)
            except queue.Empty:
                pass

            now = time.monotonic()
            if flush_requested:
                # Drain everything already queued before signalling.
                pending.extend(self._drain())
            if pending and (
                flush_requested or now >= deadline or len(pending) >= self._max_batch_size
            ):
                self._send(pending)
                pending = []
            if flush_requested:
                self._flush_done.set()
            if now >= deadline:
                deadline = now + self._flush_interval
            if self._stopped.is_set() and self._queue.empty() and not pending:
                return

    def _drain(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return items
            if item is not _FLUSH_SENTINEL:
                items.append(item)

    def _send(self, items: list[dict[str, Any]]) -> None:
        spans = [i["data"] for i in items if i["kind"] == "span"]
        traces = [i["data"] for i in items if i["kind"] == "trace"]
        # Later updates for the same trace win server-side; dedupe locally to
        # keep payloads small.
        deduped: dict[str, dict[str, Any]] = {}
        for trace in traces:
            deduped[trace["trace_id"]] = {**deduped.get(trace["trace_id"], {}), **trace}
        body = {"traces": list(deduped.values()), "spans": spans}
        self.post_batch(body)

    def post_batch(self, body: dict[str, Any]) -> None:
        backoff = 0.5
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    self._endpoint, json=body, headers=self._headers
                )
                if response.status_code < 400:
                    return
                if 400 <= response.status_code < 500:
                    logger.warning(
                        "agent-tracer: collector rejected batch (%s): %s",
                        response.status_code,
                        response.text[:500],
                    )
                    return  # not retryable
                logger.warning(
                    "agent-tracer: collector error %s (attempt %d)",
                    response.status_code,
                    attempt + 1,
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "agent-tracer: export failed (%s, attempt %d)", exc, attempt + 1
                )
            if attempt < self._max_retries:
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
        logger.error("agent-tracer: dropping batch after %d attempts", self._max_retries + 1)


class NoopExporter:
    """Used when the SDK is disabled (no API key configured)."""

    def enqueue_span(self, span_payload: dict[str, Any]) -> None:
        pass

    def enqueue_trace(self, trace_payload: dict[str, Any]) -> None:
        pass

    def flush(self, timeout: float = 10.0) -> bool:
        return True

    def shutdown(self, timeout: float = 10.0) -> None:
        pass


ExporterLike = Any  # BatchExporter | NoopExporter | test doubles

__all__ = ["BatchExporter", "ExporterLike", "NoopExporter"]
