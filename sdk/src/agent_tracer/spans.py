
from __future__ import annotations

import time
import traceback as tb_module
from datetime import datetime, timezone
from typing import Any

from .serialize import safe_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SpanHandle:
    """Mutable handle for an in-flight span. Not thread-safe by design —
    a span belongs to the task/thread that opened it."""

    def __init__(
        self,
        tracer: Any,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        name: str,
        kind: str,
        input: Any = None,
        attributes: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> None:
        self._tracer = tracer
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.name = name
        self.kind = kind
        self.started_at = _now_iso()
        self.ended_at: str | None = None
        self.status = "running"
        self.input = safe_json(input)
        self.output: Any = None
        self.attributes: dict[str, Any] = dict(attributes or {})
        self.events: list[dict[str, Any]] = []
        self.model = model
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.cache_read_tokens: int | None = None
        self.cache_creation_tokens: int | None = None
        self.reasoning_tokens: int | None = None
        self.ttft_ms: float | None = None
        self.cost_usd: float | None = None
        self._started_monotonic = time.monotonic()
        self.error: dict[str, Any] | None = None
        self._finished = False

    # ------------------------------------------------------------- mutators

    def set_input(self, value: Any) -> SpanHandle:
        self.input = safe_json(value)
        return self

    def set_output(self, value: Any) -> SpanHandle:
        self.output = safe_json(value)
        return self

    def set_attribute(self, key: str, value: Any) -> SpanHandle:
        self.attributes[key] = safe_json(value)
        return self

    def set_model(self, model: str) -> SpanHandle:
        self.model = model
        return self

    def set_usage(
        self,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        *,
        cache_read_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> SpanHandle:
        """Record token usage. `input_tokens` is *uncached* input; report
        cached tokens separately so they are priced at the cache rate."""
        if input_tokens is not None:
            self.input_tokens = int(input_tokens)
        if output_tokens is not None:
            self.output_tokens = int(output_tokens)
        if cache_read_tokens is not None:
            self.cache_read_tokens = int(cache_read_tokens)
        if cache_creation_tokens is not None:
            self.cache_creation_tokens = int(cache_creation_tokens)
        if reasoning_tokens is not None:
            self.reasoning_tokens = int(reasoning_tokens)
        if cost_usd is not None:
            self.cost_usd = float(cost_usd)
        return self

    def mark_first_token(self) -> SpanHandle:
        """Call when the first streamed token arrives (records time-to-first-token)."""
        if self.ttft_ms is None:
            self.ttft_ms = round((time.monotonic() - self._started_monotonic) * 1000.0, 3)
        return self

    def score(
        self,
        name: str,
        value: float | bool | str,
        *,
        comment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanHandle:
        """Attach a quality score to this span (number, boolean, or label)."""
        self._tracer.score(
            name,
            value,
            trace_id=self.trace_id,
            span_id=self.span_id,
            comment=comment,
            metadata=metadata,
        )
        return self

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> SpanHandle:
        self.events.append(
            {"name": name, "timestamp": _now_iso(), "attributes": safe_json(attributes) or {}}
        )
        return self

    def record_exception(self, exc: BaseException) -> SpanHandle:
        self.status = "error"
        self.error = {
            "type": type(exc).__name__,
            "message": str(exc)[:8000],
            "stacktrace": "".join(
                tb_module.format_exception(type(exc), exc, exc.__traceback__)
            )[:32000],
        }
        return self

    def end(self, status: str | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        self.ended_at = _now_iso()
        if status is not None:
            self.status = status
        elif self.status == "running":
            self.status = "ok"
        self._tracer._finish_span(self)

    # ------------------------------------------------------------ transport

    def to_payload(self, partial: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "status": "running" if partial else self.status,
            "started_at": self.started_at,
        }
        if not partial:
            payload.update(
                {
                    "ended_at": self.ended_at,
                    "input": self.input,
                    "output": self.output,
                    "attributes": self.attributes or None,
                    "events": self.events or None,
                    "model": self.model,
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "cache_read_tokens": self.cache_read_tokens,
                    "cache_creation_tokens": self.cache_creation_tokens,
                    "reasoning_tokens": self.reasoning_tokens,
                    "ttft_ms": self.ttft_ms,
                    "cost_usd": self.cost_usd,
                    "error": self.error,
                }
            )
        else:
            # Ship enough for a useful live view while the span runs.
            payload.update(
                {"input": self.input, "attributes": self.attributes or None, "model": self.model}
            )
        return payload


class TraceHandle:
    def __init__(
        self,
        tracer: Any,
        trace_id: str,
        name: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
        environment: str | None = None,
        release: str | None = None,
    ) -> None:
        self._tracer = tracer
        self.trace_id = trace_id
        self.name = name
        self.session_id = session_id
        self.metadata = metadata
        self.user_id = user_id
        self.tags = list(tags) if tags else None
        self.environment = environment
        self.release = release
        self.status: str | None = None

    def score(
        self,
        name: str,
        value: float | bool | str,
        *,
        comment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceHandle:
        """Attach a quality score to the whole trace."""
        self._tracer.score(
            name, value, trace_id=self.trace_id, comment=comment, metadata=metadata
        )
        return self

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"trace_id": self.trace_id, "name": self.name}
        if self.session_id is not None:
            payload["session_id"] = self.session_id
        if self.metadata is not None:
            payload["metadata"] = safe_json(self.metadata)
        for key in ("user_id", "tags", "environment", "release"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.status is not None:
            payload["status"] = self.status
        return payload
