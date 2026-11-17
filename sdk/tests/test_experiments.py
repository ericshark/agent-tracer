import json

import httpx
import pytest
from agent_tracer import AgentTracer, evaluator
from agent_tracer.api import ApiClient


class Sink:
    def __init__(self):
        self.spans, self.traces, self.scores = [], [], []

    def enqueue_span(self, payload):
        self.spans.append(payload)

    def enqueue_trace(self, payload):
        self.traces.append(payload)

    def enqueue_score(self, payload):
        self.scores.append(payload)

    def flush(self, timeout=10.0):
        return True

    def shutdown(self, timeout=10.0):
        pass


def make_tracer(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/v1/experiments":
            return httpx.Response(201, json={"id": "exp-1", "status": "running"})
        if request.url.path.endswith("/items"):
            return httpx.Response(201, json={"accepted": len(body["items"])})
        return httpx.Response(
            200,
            json={
                "id": "exp-1",
                "status": "completed",
                "summary": {"scores": {"exact": {"mean": 0.5}, "judge": {"mean": 0.8}}},
            },
        )

    tracer = AgentTracer(exporter=Sink())
    tracer._api = ApiClient(
        "http://collector.invalid", "at_test", transport=httpx.MockTransport(handler)
    )
    return tracer


@evaluator
def exact(output, expected):
    return output == expected


@evaluator("length")
def how_long(output):
    return len(output), "characters"


def test_experiment_runs_task_scores_and_uploads():
    calls = []
    tracer = make_tracer(calls)
    cases = [
        {"input": "a", "expected_output": "A"},
        {"input": "b", "expected_output": "nope"},
    ]
    result = tracer.experiment(
        "upper",
        dataset=cases,
        task=lambda text: text.upper(),
        evaluators=[exact, how_long],
        server_evaluators=["judge"],
        concurrency=2,
        metadata={"variant": "v2"},
    )
    assert result.status == "completed" and result.scores == {"exact": 0.5, "judge": 0.8}
    assert [i.output for i in result.items] == ["A", "B"] and result.error_count == 0

    created = next(body for _, path, body in calls if path == "/v1/experiments")
    assert created["evaluators"] == ["judge"] and created["metadata"]["variant"] == "v2"
    uploaded = next(body for _, path, body in calls if path.endswith("/items"))["items"]
    first = uploaded[0]
    assert first["trace_id"] and first["latency_ms"] >= 0
    assert {"name": "exact", "value": True} in first["scores"]
    assert {"name": "length", "value": 1, "comment": "characters"} in first["scores"]
    assert {"name": "exact", "value": False} in uploaded[1]["scores"]
    assert any(path.endswith("/complete") for _, path, _ in calls)

    # Each case was traced as experiment traffic with a task span.
    exporter = tracer._exporter
    assert {t["environment"] for t in exporter.traces} == {"experiment"}
    assert sum(1 for s in exporter.spans if s["name"] == "task" and s["status"] == "ok") == 2


def test_failing_task_is_recorded_not_raised():
    calls = []
    tracer = make_tracer(calls)

    def task(value):
        if value == "bad":
            raise RuntimeError("boom")
        return value

    result = tracer.experiment(
        "flaky", dataset=[{"input": "ok"}, {"input": "bad"}], task=task, evaluators=[how_long]
    )
    assert result.error_count == 1
    uploaded = next(body for _, path, body in calls if path.endswith("/items"))["items"]
    assert uploaded[1]["error"] == "RuntimeError: boom" and uploaded[1]["scores"] == []


def test_async_task_and_empty_dataset():
    tracer = make_tracer([])

    async def task(value):
        return value * 2

    result = tracer.experiment("async", dataset=[{"input": 2}], task=task)
    assert result.items[0].output == 4
    with pytest.raises(ValueError, match="no items"):
        tracer.experiment("empty", dataset=[], task=task)
