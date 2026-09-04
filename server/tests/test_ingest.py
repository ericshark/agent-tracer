import uuid
from datetime import UTC

from tests.conftest import make_span


def auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def test_ingest_requires_api_key(client):
    assert (await client.post("/v1/ingest", json={"spans": []})).status_code == 401
    bad = await client.post(
        "/v1/ingest", json={"spans": []}, headers={"X-API-Key": "at_" + "0" * 48}
    )
    assert bad.status_code == 401


async def test_ingest_creates_trace_and_spans(user_client, project, api_key):
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex
    root = make_span(trace_id, "a" * 16, name="support-agent", kind="AGENT")
    child = make_span(
        trace_id,
        "b" * 16,
        parent="a" * 16,
        name="claude-call",
        kind="LLM",
        model="claude-opus-5",
        input_tokens=1000,
        output_tokens=500,
        input={"messages": [{"role": "user", "content": "hi"}]},
        output={"role": "assistant", "content": "hello"},
    )
    response = await client.post(
        "/v1/ingest", json={"spans": [root, child]}, headers=auth(api_key)
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"accepted_traces": 1, "accepted_spans": 2}

    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    items = listed.json()["items"]
    assert len(items) == 1
    trace = items[0]
    assert trace["name"] == "support-agent"
    assert trace["status"] == "ok"
    assert trace["span_count"] == 2
    assert trace["llm_call_count"] == 1
    assert trace["input_tokens"] == 1000
    assert trace["output_tokens"] == 500
    # claude-opus-5: $5/M input + $25/M output
    assert abs(trace["cost_usd"] - (1000 * 5 + 500 * 25) / 1_000_000) < 1e-9

    detail = await client.get(f"/api/traces/{trace['id']}", headers=headers)
    spans = detail.json()["spans"]
    assert [s["name"] for s in spans] == ["support-agent", "claude-call"]
    assert spans[1]["cost_usd"] is not None


async def test_span_upsert_start_then_end(user_client, project, api_key):
    """The SDK streams a span at start and completes it later — same span row."""
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex
    start = make_span(
        trace_id, "c" * 16, name="tool-call", kind="TOOL", status="running", ended_at=None
    )
    response = await client.post("/v1/ingest", json={"spans": [start]}, headers=auth(api_key))
    assert response.status_code == 200

    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace = listed.json()["items"][0]
    assert trace["status"] == "running"

    end = make_span(
        trace_id,
        "c" * 16,
        name="tool-call",
        kind="TOOL",
        status="ok",
        output={"result": 42},
    )
    await client.post("/v1/ingest", json={"spans": [end]}, headers=auth(api_key))

    detail = await client.get(f"/api/traces/{trace['id']}", headers=headers)
    body = detail.json()
    assert body["span_count"] == 1
    assert body["status"] == "ok"
    assert body["spans"][0]["output"] == {"result": 42}
    assert body["spans"][0]["duration_ms"] is not None


async def test_error_span_marks_trace_errored(user_client, project, api_key):
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex
    span = make_span(
        trace_id,
        "d" * 16,
        name="failing-tool",
        kind="TOOL",
        status="error",
        error={
            "type": "TimeoutError",
            "message": "the weather API timed out",
            "stacktrace": "Traceback ...",
        },
    )
    await client.post("/v1/ingest", json={"spans": [span]}, headers=auth(api_key))
    listed = await client.get(
        f"/api/projects/{project['id']}/traces?status=error", headers=headers
    )
    trace = listed.json()["items"][0]
    assert trace["status"] == "error"
    assert trace["error_count"] == 1

    detail = await client.get(f"/api/traces/{trace['id']}", headers=headers)
    assert detail.json()["spans"][0]["error_message"] == "the weather API timed out"


async def test_trace_metadata_upsert(user_client, project, api_key):
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex
    payload = {
        "traces": [
            {
                "trace_id": trace_id,
                "name": "checkout-flow",
                "session_id": "sess-9",
                "metadata": {"env": "staging"},
            }
        ],
        "spans": [make_span(trace_id, "e" * 16, name="root")],
    }
    await client.post("/v1/ingest", json=payload, headers=auth(api_key))
    listed = await client.get(
        f"/api/projects/{project['id']}/traces?session_id=sess-9", headers=headers
    )
    trace = listed.json()["items"][0]
    assert trace["name"] == "checkout-flow"
    assert trace["meta"] == {"env": "staging"}


async def test_invalid_span_ids_rejected(client, api_key):
    bad = make_span("not-hex", "zzz")
    response = await client.post("/v1/ingest", json={"spans": [bad]}, headers=auth(api_key))
    assert response.status_code == 422


async def test_oversized_payload_truncated_not_rejected(user_client, project, api_key):
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex
    span = make_span(trace_id, "f" * 16, input={"blob": "x" * 400_000})
    response = await client.post("/v1/ingest", json={"spans": [span]}, headers=auth(api_key))
    assert response.status_code == 200
    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace_pk = listed.json()["items"][0]["id"]
    detail = await client.get(f"/api/traces/{trace_pk}", headers=headers)
    stored_input = detail.json()["spans"][0]["input"]
    assert stored_input["_truncated"] is True


async def test_stats_endpoint(user_client, project, api_key):
    from datetime import datetime, timedelta

    client, headers, _user = user_client
    now = datetime.now(UTC)
    for i in range(3):
        trace_id = uuid.uuid4().hex
        started = (now - timedelta(minutes=10 + i)).isoformat()
        ended = (now - timedelta(minutes=9 + i)).isoformat()
        span = make_span(
            trace_id,
            uuid.uuid4().hex[:16],
            name="run",
            started_at=started,
            ended_at=ended,
            status="error" if i == 0 else "ok",
            input_tokens=100,
            output_tokens=50,
        )
        await client.post("/v1/ingest", json={"spans": [span]}, headers=auth(api_key))

    stats = await client.get(f"/api/projects/{project['id']}/stats?hours=24", headers=headers)
    body = stats.json()
    assert body["trace_count"] == 3
    assert body["error_count"] == 1
    assert 0.3 < body["error_rate"] < 0.4
    assert body["total_input_tokens"] == 300
    assert len(body["buckets"]) >= 12
    assert sum(b["trace_count"] for b in body["buckets"]) == 3
