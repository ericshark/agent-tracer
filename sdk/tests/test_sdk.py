import asyncio

import pytest
from agent_tracer import AgentTracer, current_span, current_trace


class CapturingExporter:
    """Test double that records everything the tracer would ship."""

    def __init__(self):
        self.spans = []
        self.traces = []

    def enqueue_span(self, payload):
        self.spans.append(payload)

    def enqueue_trace(self, payload):
        self.traces.append(payload)

    def flush(self, timeout=10.0):
        return True

    def shutdown(self, timeout=10.0):
        pass

    def completed_spans(self):
        return [s for s in self.spans if s["status"] != "running"]


@pytest.fixture
def tracer_and_exporter():
    exporter = CapturingExporter()
    return AgentTracer(exporter=exporter), exporter


def test_trace_and_nested_spans(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter
    with tracer.trace("run", session_id="s-1", metadata={"env": "test"}):
        with tracer.agent("router"):
            msgs = [{"role": "user", "content": "hi"}]
            with tracer.llm(model="claude-opus-5", messages=msgs) as llm:
                llm.set_output("hello").set_usage(input_tokens=10, output_tokens=5)
            with tracer.tool("search", input={"q": "docs"}) as tool:
                tool.set_output([1, 2, 3])

    completed = exporter.completed_spans()
    assert [s["name"] for s in completed] == ["claude-opus-5", "search", "router"]

    llm_span, tool_span, agent_span_payload = completed
    assert llm_span["kind"] == "LLM"
    assert llm_span["model"] == "claude-opus-5"
    assert llm_span["input"] == {"messages": [{"role": "user", "content": "hi"}]}
    assert llm_span["output"] == "hello"
    assert llm_span["input_tokens"] == 10
    assert llm_span["parent_span_id"] == agent_span_payload["span_id"]

    assert tool_span["kind"] == "TOOL"
    assert tool_span["parent_span_id"] == agent_span_payload["span_id"]

    assert agent_span_payload["parent_span_id"] is None
    trace_ids = {s["trace_id"] for s in completed}
    assert len(trace_ids) == 1

    # Trace lifecycle: initial record, root-span close, context-exit close.
    assert exporter.traces[0]["name"] == "run"
    assert exporter.traces[0]["session_id"] == "s-1"
    assert exporter.traces[-1]["status"] == "ok"


def test_span_start_shipped_immediately(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter
    with tracer.span("outer"):
        running = [s for s in exporter.spans if s["status"] == "running"]
        assert len(running) == 1
        assert running[0]["name"] == "outer"


def test_exception_recorded_and_reraised(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter
    with pytest.raises(ValueError, match="kaboom"), tracer.trace("failing-run"):
        with tracer.tool("broken"):
            raise ValueError("kaboom")

    span = exporter.completed_spans()[0]
    assert span["status"] == "error"
    assert span["error"]["type"] == "ValueError"
    assert span["error"]["message"] == "kaboom"
    assert "ValueError: kaboom" in span["error"]["stacktrace"]
    assert exporter.traces[-1]["status"] == "error"


def test_implicit_trace_created(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter
    with tracer.tool("standalone") as span:
        assert current_trace() is not None
        assert current_span() is span
    assert current_trace() is None

    assert len(exporter.traces) >= 2  # created + closed
    assert exporter.traces[0]["name"] == "standalone"
    assert exporter.traces[-1]["status"] == "ok"
    assert exporter.completed_spans()[0]["parent_span_id"] is None


def test_observe_decorator_sync(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter

    @tracer.observe(kind="TOOL")
    def lookup(city: str, units: str = "C"):
        return {"temp": 21, "city": city}

    assert lookup("Paris") == {"temp": 21, "city": "Paris"}
    span = exporter.completed_spans()[0]
    assert span["name"] == "lookup"
    assert span["kind"] == "TOOL"
    assert span["input"] == {"city": "Paris", "units": "C"}
    assert span["output"] == {"temp": 21, "city": "Paris"}


def test_observe_decorator_async(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter

    @tracer.observe(kind="AGENT", name="pipeline")
    async def run(x: int):
        await asyncio.sleep(0)
        return x * 2

    assert asyncio.run(run(21)) == 42
    span = exporter.completed_spans()[0]
    assert span["name"] == "pipeline"
    assert span["kind"] == "AGENT"
    assert span["output"] == 42


def test_observe_decorator_captures_errors(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter

    @tracer.observe
    def explode():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        explode()
    span = exporter.completed_spans()[0]
    assert span["status"] == "error"
    assert span["error"]["type"] == "RuntimeError"


def test_events_and_attributes(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter
    with tracer.span("step") as span:
        span.set_attribute("retry", 2)
        span.add_event("cache.miss", {"key": "abc"})
    payload = exporter.completed_spans()[0]
    assert payload["attributes"] == {"retry": 2}
    assert payload["events"][0]["name"] == "cache.miss"
    assert payload["events"][0]["attributes"] == {"key": "abc"}


def test_oversized_values_truncated(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter
    with tracer.span("big") as span:
        span.set_output("y" * 200_000)
    payload = exporter.completed_spans()[0]
    assert payload["output"]["_truncated"] is True


def test_unserializable_values_survive(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter

    class Weird:
        def __repr__(self):
            return "<weird object>"

    with tracer.span("odd") as span:
        span.set_output({"obj": Weird()})
    payload = exporter.completed_spans()[0]
    assert payload["output"]["obj"] == "<weird object>"


def test_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("AGENT_TRACER_API_KEY", raising=False)
    tracer = AgentTracer()  # no key → no-op, must not raise
    with tracer.trace("run"), tracer.span("noop") as span:
        span.set_output("fine")
    assert tracer.flush() is True


def test_ids_are_w3c_format(tracer_and_exporter):
    tracer, exporter = tracer_and_exporter
    with tracer.span("x"):
        pass
    span = exporter.completed_spans()[0]
    assert len(span["trace_id"]) == 32
    assert len(span["span_id"]) == 16
    int(span["trace_id"], 16)
    int(span["span_id"], 16)


def test_threaded_spans_do_not_leak_context(tracer_and_exporter):
    import threading

    tracer, exporter = tracer_and_exporter
    results = {}

    def worker(name):
        with tracer.span(name):
            results[name] = current_span().name

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == {f"t{i}": f"t{i}" for i in range(4)}
    # each thread created its own implicit trace
    trace_ids = {s["trace_id"] for s in exporter.completed_spans()}
    assert len(trace_ids) == 4
