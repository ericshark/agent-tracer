import asyncio
import json
import uuid

from tests.conftest import make_span

# NOTE: httpx's ASGITransport buffers streaming responses until the app
# completes, so these tests use the endpoint's `limit` parameter to close the
# stream after the expected number of events. True long-lived streaming is
# exercised against a real server in the SDK end-to-end demo.


async def test_live_stream_receives_ingest_events(user_client, project, api_key):
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex

    async def consume() -> list[dict]:
        events = []
        async with client.stream(
            "GET", f"/api/projects/{project['id']}/events?limit=2", headers=headers
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.2)  # let the subscription attach

    span = make_span(trace_id, "a1" * 8, name="live-span", kind="AGENT")
    ingest = await client.post(
        "/v1/ingest",
        json={"spans": [span]},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert ingest.status_code == 200

    received = await asyncio.wait_for(consumer, timeout=5)
    types = [e["type"] for e in received]
    assert types[0] == "connected"
    assert "span.upserted" in types
    assert "trace.updated" in types
    span_event = next(e for e in received if e["type"] == "span.upserted")
    assert span_event["trace_id"] == trace_id
    assert span_event["span"]["name"] == "live-span"
    trace_event = next(e for e in received if e["type"] == "trace.updated")
    assert trace_event["trace"]["span_count"] == 1


async def test_live_stream_trace_filter(user_client, project, api_key):
    client, headers, _user = user_client
    wanted = uuid.uuid4().hex
    other = uuid.uuid4().hex

    async def consume() -> list[dict]:
        events = []
        async with client.stream(
            "GET",
            f"/api/projects/{project['id']}/events?trace_id={wanted}&limit=2",
            headers=headers,
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.2)

    key_headers = {"Authorization": f"Bearer {api_key}"}
    await client.post(
        "/v1/ingest", json={"spans": [make_span(other, "b2" * 8)]}, headers=key_headers
    )
    await client.post(
        "/v1/ingest", json={"spans": [make_span(wanted, "c3" * 8)]}, headers=key_headers
    )
    received = await asyncio.wait_for(consumer, timeout=5)

    trace_ids = {
        e.get("trace_id") or e.get("trace", {}).get("trace_id")
        for e in received
        if e["type"] != "connected"
    }
    assert trace_ids == {wanted}


async def test_live_stream_requires_auth(client, project):
    response = await client.get(f"/api/projects/{project['id']}/events")
    assert response.status_code == 401


async def test_live_stream_accepts_query_token(user_client, project, api_key):
    """EventSource clients can't set headers; a ?token= query param works."""
    client, headers, _user = user_client
    token = headers["Authorization"].removeprefix("Bearer ")

    async def consume() -> list[dict]:
        events = []
        async with client.stream(
            "GET", f"/api/projects/{project['id']}/events?limit=1&token={token}"
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.2)
    await client.post(
        "/v1/ingest",
        json={"spans": [make_span(uuid.uuid4().hex, "d4" * 8)]},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    received = await asyncio.wait_for(consumer, timeout=5)
    assert len(received) >= 2  # connected + at least one event
