import uuid

from tests.conftest import make_span


async def ingest_llm_span(client, api_key: str, **span_overrides) -> str:
    trace_id = uuid.uuid4().hex
    defaults = dict(
        name="claude-call",
        kind="LLM",
        status="error",
        model="claude-opus-5",
        input={
            "messages": [{"role": "user", "content": "What is the refund policy?"}],
            "system": "You are a support agent.",
        },
        error={"type": "RateLimitError", "message": "429"},
    )
    defaults.update(span_overrides)
    span = make_span(trace_id, "ab" * 8, **defaults)
    response = await client.post(
        "/v1/ingest", json={"spans": [span]}, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert response.status_code == 200
    return trace_id


async def get_span_pk(client, headers, project_id: str) -> str:
    listed = await client.get(f"/api/projects/{project_id}/traces", headers=headers)
    trace_pk = listed.json()["items"][0]["id"]
    detail = await client.get(f"/api/traces/{trace_pk}", headers=headers)
    return detail.json()["spans"][0]["id"]


async def test_replay_simulation_provider(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_llm_span(client, api_key)
    span_pk = await get_span_pk(client, headers, project["id"])

    response = await client.post(
        f"/api/spans/{span_pk}/replays", json={}, headers=headers
    )
    assert response.status_code == 201, response.text
    replay = response.json()
    assert replay["provider"] == "simulation"
    assert replay["status"] == "ok"
    assert replay["model"] == "claude-opus-5"
    assert replay["output"]["simulated"] is True
    assert "refund policy" in replay["output"]["content"]
    assert replay["latency_ms"] > 0
    # recorded input is preserved for auditability
    assert replay["input"]["messages"][0]["content"] == "What is the refund policy?"
    assert replay["input"]["system"] == "You are a support agent."

    listed = await client.get(f"/api/spans/{span_pk}/replays", headers=headers)
    assert len(listed.json()) == 1


async def test_replay_with_edited_input(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_llm_span(client, api_key)
    span_pk = await get_span_pk(client, headers, project["id"])

    response = await client.post(
        f"/api/spans/{span_pk}/replays",
        json={
            "messages": [{"role": "user", "content": "EDITED prompt"}],
            "model": "claude-sonnet-5",
            "params": {"max_tokens": 128},
        },
        headers=headers,
    )
    replay = response.json()
    assert replay["model"] == "claude-sonnet-5"
    assert replay["input"]["messages"][0]["content"] == "EDITED prompt"
    assert replay["input"]["params"]["max_tokens"] == 128


async def test_replay_rejects_non_llm_span(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_llm_span(client, api_key, kind="TOOL")
    span_pk = await get_span_pk(client, headers, project["id"])
    response = await client.post(f"/api/spans/{span_pk}/replays", json={}, headers=headers)
    assert response.status_code == 400
    assert "LLM" in response.json()["detail"]


async def test_replay_requires_provider_credential_for_real_calls(
    user_client, project, api_key
):
    client, headers, _user = user_client
    await ingest_llm_span(client, api_key)
    span_pk = await get_span_pk(client, headers, project["id"])
    response = await client.post(
        f"/api/spans/{span_pk}/replays", json={"provider": "anthropic"}, headers=headers
    )
    assert response.status_code == 400
    assert "API key" in response.json()["detail"]


async def test_replay_never_mutates_original_span(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_llm_span(client, api_key)
    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace_pk = listed.json()["items"][0]["id"]
    before = (await client.get(f"/api/traces/{trace_pk}", headers=headers)).json()

    span_pk = before["spans"][0]["id"]
    await client.post(f"/api/spans/{span_pk}/replays", json={}, headers=headers)

    after = (await client.get(f"/api/traces/{trace_pk}", headers=headers)).json()
    assert after["spans"] == before["spans"]
    assert after["status"] == before["status"]
