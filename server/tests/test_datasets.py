import uuid

from tests.conftest import make_span


def key_auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _dataset(client, headers, project, name="regressions"):
    response = await client.post(
        f"/api/projects/{project['id']}/datasets", json={"name": name}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_dataset_crud_and_items(user_client, project):
    client, headers, _ = user_client
    dataset = await _dataset(client, headers, project)
    dup = await client.post(
        f"/api/projects/{project['id']}/datasets", json={"name": "regressions"}, headers=headers
    )
    assert dup.status_code == 409

    created = await client.post(
        f"/api/datasets/{dataset['id']}/items",
        json={
            "items": [
                {"input": {"q": "2+2"}, "expected_output": "4", "metadata": {"topic": "math"}},
                {"input": "hello"},
            ]
        },
        headers=headers,
    )
    assert created.status_code == 201 and len(created.json()) == 2
    item_id = created.json()[0]["id"]

    patched = await client.patch(
        f"/api/dataset-items/{item_id}", json={"expected_output": None}, headers=headers
    )
    assert patched.json()["expected_output"] is None and patched.json()["input"] == {"q": "2+2"}

    await client.patch(f"/api/dataset-items/{item_id}", json={"archived": True}, headers=headers)
    listing = (await client.get(f"/api/datasets/{dataset['id']}/items", headers=headers)).json()
    assert listing["total"] == 1
    with_archived = await client.get(
        f"/api/datasets/{dataset['id']}/items?include_archived=true", headers=headers
    )
    assert with_archived.json()["total"] == 2

    datasets = (await client.get(f"/api/projects/{project['id']}/datasets", headers=headers)).json()
    assert datasets[0]["item_count"] == 1

    assert (
        await client.delete(f"/api/datasets/{dataset['id']}", headers=headers)
    ).status_code == 204
    assert (await client.get(f"/api/datasets/{dataset['id']}", headers=headers)).status_code == 404


async def test_capture_items_from_traces(user_client, project, api_key):
    client, headers, _ = user_client
    trace_id = uuid.uuid4().hex
    root_id, child_id = uuid.uuid4().hex[:16], uuid.uuid4().hex[:16]
    await client.post(
        "/v1/ingest",
        json={
            "spans": [
                make_span(
                    trace_id=trace_id,
                    span_id=root_id,
                    name="agent",
                    input={"question": "weather?"},
                    output={"answer": "sunny"},
                ),
                make_span(
                    trace_id=trace_id,
                    span_id=child_id,
                    parent=root_id,
                    kind="LLM",
                    name="plan",
                    started_at="2026-08-04T12:00:00.5+00:00",
                    input={"messages": [{"role": "user", "content": "weather?"}]},
                    output={"role": "assistant", "content": "check the forecast"},
                ),
            ]
        },
        headers=key_auth(api_key),
    )
    trace = (await client.get(f"/api/projects/{project['id']}/traces", headers=headers)).json()[
        "items"
    ][0]
    detail = (await client.get(f"/api/traces/{trace['id']}", headers=headers)).json()
    llm_pk = next(s["id"] for s in detail["spans"] if s["kind"] == "LLM")

    dataset = await _dataset(client, headers, project)
    response = await client.post(
        f"/api/datasets/{dataset['id']}/items/from-traces",
        json={"sources": [{"trace_pk": trace["id"]}, {"trace_pk": trace["id"], "span_pk": llm_pk}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    from_root, from_llm = response.json()
    assert from_root["input"] == {"question": "weather?"}
    assert from_root["expected_output"] == {"answer": "sunny"}
    assert from_llm["source_span_pk"] == llm_pk
    assert from_llm["expected_output"]["content"] == "check the forecast"


async def test_import_and_export(user_client, project):
    client, headers, _ = user_client
    dataset = await _dataset(client, headers, project)
    url = f"/api/datasets/{dataset['id']}"

    jsonl = '{"input": {"q": "a"}, "expected_output": "A"}\n\n{"question": "b"}\n'
    imported = await client.post(
        f"{url}/import", json={"format": "jsonl", "content": jsonl}, headers=headers
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()[1]["input"] == {"question": "b"}

    csv_text = 'question,lang,expected_output\n"hi",en,"{""ok"": true}"\n'
    imported = await client.post(
        f"{url}/import", json={"format": "csv", "content": csv_text}, headers=headers
    )
    row = imported.json()[0]
    assert row["input"] == {"question": "hi", "lang": "en"} and row["expected_output"] == {
        "ok": True
    }

    bad = await client.post(
        f"{url}/import", json={"format": "jsonl", "content": "{not json"}, headers=headers
    )
    assert bad.status_code == 400 and "Line 1" in bad.json()["detail"]

    exported = await client.get(f"{url}/export", headers=headers)
    lines = exported.text.strip().splitlines()
    assert len(lines) == 3 and '"expected_output": "A"' in lines[0]


async def test_sdk_dataset_api_and_scopes(user_client, project, api_key):
    client, headers, _ = user_client
    created = await client.post(
        "/v1/datasets", json={"name": "from-sdk"}, headers=key_auth(api_key)
    )
    assert created.status_code == 200
    again = await client.post("/v1/datasets", json={"name": "from-sdk"}, headers=key_auth(api_key))
    assert again.json()["id"] == created.json()["id"]

    added = await client.post(
        "/v1/datasets/from-sdk/items",
        json={"items": [{"input": 1, "expected_output": 2}]},
        headers=key_auth(api_key),
    )
    assert added.status_code == 201
    fetched = await client.get("/v1/datasets/from-sdk", headers=key_auth(api_key))
    assert fetched.json()["item_count"] == 1 and fetched.json()["items"][0]["input"] == 1
    assert (await client.get("/v1/datasets/nope", headers=key_auth(api_key))).status_code == 404

    ingest_only = await client.post(
        f"/api/projects/{project['id']}/api-keys",
        json={"name": "ingest", "scopes": ["ingest"]},
        headers=headers,
    )
    denied = await client.get("/v1/datasets", headers=key_auth(ingest_only.json()["key"]))
    assert denied.status_code == 403


async def test_datasets_are_isolated_between_users(user_client, project, client):
    owner_client, headers, _ = user_client
    dataset = await _dataset(owner_client, headers, project)
    other = await client.post(
        "/api/auth/register",
        json={"email": "other-ds@example.com", "name": "Other", "password": "sup3r-secret-pw"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (
        await client.get(f"/api/datasets/{dataset['id']}/items", headers=other_headers)
    ).status_code == 404
