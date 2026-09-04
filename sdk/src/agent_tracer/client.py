
from __future__ import annotations

import contextvars
import functools
import inspect
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from .exporter import BatchExporter, ExporterLike, NoopExporter
from .ids import new_span_id, new_trace_id
from .spans import SpanHandle, TraceHandle

logger = logging.getLogger("agent_tracer")

_current_trace: contextvars.ContextVar[TraceHandle | None] = contextvars.ContextVar(
    "agent_tracer_current_trace", default=None
)
_current_span: contextvars.ContextVar[SpanHandle | None] = contextvars.ContextVar(
    "agent_tracer_current_span", default=None
)


class AgentTracer:
    """Entry point for instrumenting an application.

        from agent_tracer import AgentTracer

        tracer = AgentTracer(api_key="at_…", base_url="http://localhost:8000")

        with tracer.trace("support-run", session_id="user-42"):
            with tracer.agent("router"):
                with tracer.llm(model="claude-opus-5", messages=msgs) as llm:
                    reply = call_model(msgs)
                    llm.set_output(reply).set_usage(input_tokens=812, output_tokens=310)

    Spans are exported by a background thread; nothing here blocks the host
    application. If no API key is available the tracer becomes a no-op.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        flush_interval: float = 0.5,
        exporter: ExporterLike | None = None,
    ) -> None:
        api_key = api_key or os.environ.get("AGENT_TRACER_API_KEY")
        base_url = (
            base_url
            or os.environ.get("AGENT_TRACER_BASE_URL")
            or "http://localhost:8000"
        )
        if exporter is not None:
            self._exporter: ExporterLike = exporter
        elif api_key:
            self._exporter = BatchExporter(base_url, api_key, flush_interval=flush_interval)
        else:
            logger.warning(
                "agent-tracer: no API key configured (AGENT_TRACER_API_KEY) — tracing disabled"
            )
            self._exporter = NoopExporter()

    # ---------------------------------------------------------------- traces

    @contextmanager
    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> Iterator[TraceHandle]:
        """Open a trace: one end-to-end execution of your agent."""
        handle = TraceHandle(
            self, trace_id or new_trace_id(), name, session_id=session_id, metadata=metadata
        )
        self._exporter.enqueue_trace(handle.to_payload())
        token = _current_trace.set(handle)
        try:
            yield handle
        except BaseException:
            handle.status = "error"
            raise
        else:
            if handle.status is None:
                handle.status = "ok"
        finally:
            _current_trace.reset(token)
            self._exporter.enqueue_trace(handle.to_payload())

    # ----------------------------------------------------------------- spans

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: str = "CHAIN",
        input: Any = None,
        attributes: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> Iterator[SpanHandle]:
        """Open a span inside the current trace (a trace is created implicitly
        if none is active). Exceptions are recorded and re-raised."""
        trace = _current_trace.get()
        implicit_trace_token = None
        if trace is None:
            trace = TraceHandle(self, new_trace_id(), name)
            self._exporter.enqueue_trace(trace.to_payload())
            implicit_trace_token = _current_trace.set(trace)

        parent = _current_span.get()
        span = SpanHandle(
            tracer=self,
            trace_id=trace.trace_id,
            span_id=new_span_id(),
            parent_span_id=parent.span_id if parent else None,
            name=name,
            kind=kind,
            input=input,
            attributes=attributes,
            model=model,
        )
        span._trace = trace
        # Ship the start immediately so the live view shows in-flight work.
        self._exporter.enqueue_span(span.to_payload(partial=True))
        span_token = _current_span.set(span)
        try:
            yield span
        except BaseException as exc:
            span.record_exception(exc)
            raise
        finally:
            _current_span.reset(span_token)
            if implicit_trace_token is not None:
                _current_trace.reset(implicit_trace_token)
            span.end()

    def agent(self, name: str, **kwargs: Any) -> Any:
        """Span for one agent step / run."""
        return self.span(name, kind="AGENT", **kwargs)

    def tool(self, name: str, **kwargs: Any) -> Any:
        """Span for a tool invocation."""
        return self.span(name, kind="TOOL", **kwargs)

    def chain(self, name: str, **kwargs: Any) -> Any:
        """Span for an intermediate pipeline step."""
        return self.span(name, kind="CHAIN", **kwargs)

    def retriever(self, name: str, **kwargs: Any) -> Any:
        """Span for a retrieval / vector-search step."""
        return self.span(name, kind="RETRIEVER", **kwargs)

    def llm(
        self,
        model: str,
        *,
        name: str | None = None,
        messages: list | None = None,
        system: str | None = None,
        input: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Span for a model call. Pass the request `messages` (and optional
        `system`); record the response with `set_output()` / `set_usage()`."""
        if input is None and (messages is not None or system is not None):
            input = {"messages": messages or []}
            if system is not None:
                input["system"] = system
        return self.span(name or model, kind="LLM", input=input, model=model, **kwargs)

    # ------------------------------------------------------------- decorator

    def observe(
        self,
        name_or_func: Any = None,
        *,
        kind: str = "CHAIN",
        name: str | None = None,
        capture_args: bool = True,
        capture_result: bool = True,
    ) -> Callable:
        """Decorator form: trace a function as a span.

            @tracer.observe(kind="TOOL")
            def search(query: str) -> list: ...

        Works on both sync and async functions.
        """

        def decorate(func: Callable) -> Callable:
            span_name = name or getattr(func, "__name__", "span")

            def build_input(args: tuple, kwargs: dict) -> Any:
                if not capture_args:
                    return None
                try:
                    bound = inspect.signature(func).bind_partial(*args, **kwargs)
                    bound.apply_defaults()
                    return {
                        k: v for k, v in bound.arguments.items() if k not in ("self", "cls")
                    }
                except (TypeError, ValueError):
                    return None

            if inspect.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    with self.span(
                        span_name, kind=kind, input=build_input(args, kwargs)
                    ) as span:
                        result = await func(*args, **kwargs)
                        if capture_result:
                            span.set_output(result)
                        return result

                return async_wrapper

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.span(span_name, kind=kind, input=build_input(args, kwargs)) as span:
                    result = func(*args, **kwargs)
                    if capture_result:
                        span.set_output(result)
                    return result

            return wrapper

        if callable(name_or_func):  # bare @tracer.observe
            return decorate(name_or_func)
        if isinstance(name_or_func, str):
            name = name or name_or_func
        return decorate

    # -------------------------------------------------------------- plumbing

    def _finish_span(self, span: SpanHandle) -> None:
        self._exporter.enqueue_span(span.to_payload())
        # A finishing root span closes its (explicitly-named or implicit) trace.
        trace = getattr(span, "_trace", None)
        if trace is not None and span.parent_span_id is None:
            trace.status = "error" if span.status == "error" else "ok"
            self._exporter.enqueue_trace(trace.to_payload())

    def flush(self, timeout: float = 10.0) -> bool:
        """Block until all queued telemetry has been delivered."""
        return self._exporter.flush(timeout)

    def shutdown(self, timeout: float = 10.0) -> None:
        self._exporter.shutdown(timeout)


def current_span() -> SpanHandle | None:
    """The span currently active in this task/thread, if any."""
    return _current_span.get()


def current_trace() -> TraceHandle | None:
    """The trace currently active in this task/thread, if any."""
    return _current_trace.get()
