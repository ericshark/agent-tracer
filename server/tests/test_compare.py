import uuid

from tests.conftest import make_span


async def ingest_pipeline(client, api_key: str, fail_tool: bool) -> str:
    """Two runs of the same pipeline; one fails at the tool step."""
    trace_id = uuid.uuid4().hex
    root = make_span(trace_id, "aa" * 8, name="pipeline", kind="AGENT")
    llm = make_span(
        trace_id,
        "bb" * 8,
        parent="aa" * 8,
        name="plan",
        kind="LLM",
        model="claude-opus-5",
        input_tokens=500,
        output_tokens=200,
        output={"role": "assistant", "content": "plan A" if fail_tool else "plan B"},
    )
    tool = make_span(
        trace_id,
        "cc" * 8,
        parent="aa" * 8,
        name="search",
        kind="TOOL",
        status="error" if fail_tool else "ok",
        error={"type": "HTTPError", "message": "503"} if fail_tool else None,
    )
    spans = [root, llm, tool]
    if not fail_tool:
        spans.append(
            make_span(trace_id, "dd" * 8, parent="aa" * 8, name="answer", kind="LLM")
        )
    response = await client.post(
        "/v1/ingest", json={"spans": spans}, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert response.status_code == 200
    return trace_id


async def test_compare_traces(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_pipeline(client, api_key, fail_tool=True)
    await ingest_pipeline(client, api_key, fail_tool=False)

    listed = await client.get(
        f"/api/projects/{project['id']}/traces", headers=headers
    )
    items = listed.json()["items"]
    failed = next(t for t in items if t["status"] == "error")
    passed = next(t for t in items if t["status"] == "ok")

    response = await client.get(
        f"/api/compare?base={failed['id']}&other={passed['id']}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()

    assert body["summary"]["matched"] == 3  # pipeline, plan, search
    assert body["summary"]["added"] == 1  # the extra "answer" span
    assert body["summary"]["removed"] == 0
    assert body["summary"]["changed"] >= 1

    root = body["nodes"][0]
    assert root["change"] == "matched"
    names = {c["base"]["name"] if c["base"] else c["other"]["name"]: c for c in root["children"]}
    assert names["search"]["delta"]["status_changed"] is True
    assert names["plan"]["delta"]["output_changed"] is True
    assert names["answer"]["change"] == "added"


async def test_compare_rejects_foreign_traces(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_pipeline(client, api_key, fail_tool=False)
    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    mine = listed.json()["items"][0]["id"]

    other_user = await client.post(
        "/api/auth/register",
        json={"email": "rival@example.com", "name": "Rival", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other_user.json()['access_token']}"}
    response = await client.get(
        f"/api/compare?base={mine}&other={mine}", headers=other_headers
    )
    assert response.status_code == 404
