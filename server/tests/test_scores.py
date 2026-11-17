import uuid

from tests.conftest import make_span


def key_auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _ingest_trace(client, api_key, **span):
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    response = await client.post(
        "/v1/ingest",
        json={"spans": [make_span(trace_id=trace_id, span_id=span_id, **span)]},
        headers=key_auth(api_key),
    )
    assert response.status_code == 200, response.text
    return trace_id, span_id


async def _trace(client, headers, project):
    listing = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    return listing.json()["items"][0]


async def test_scores_ride_along_with_ingest_batch(user_client, project, api_key):
    client, headers, _ = user_client
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    response = await client.post(
        "/v1/ingest",
        json={
            "spans": [make_span(trace_id=trace_id, span_id=span_id)],
            "scores": [
                {"trace_id": trace_id, "span_id": span_id, "name": "accuracy", "value": 0.8},
                {"trace_id": trace_id, "name": "passed", "value": True},
                {"trace_id": trace_id, "name": "tone", "value": "friendly"},
                {"trace_id": uuid.uuid4().hex, "name": "orphan", "value": 1},
            ],
        },
        headers=key_auth(api_key),
    )
    assert response.json()["accepted_scores"] == 3

    trace = await _trace(client, headers, project)
    assert trace["scores"] == {"accuracy": 0.8, "passed": 1.0, "tone": "friendly"}
    scores = (await client.get(f"/api/traces/{trace['id']}/scores", headers=headers)).json()
    by_name = {s["name"]: s for s in scores}
    assert by_name["accuracy"]["span_pk"] is not None and by_name["accuracy"]["source"] == "sdk"
    assert by_name["passed"]["data_type"] == "boolean"
    assert by_name["tone"]["string_value"] == "friendly" and by_name["tone"]["value"] is None


async def test_v1_score_endpoint_and_idempotency(user_client, project, api_key):
    client, headers, _ = user_client
    trace_id, _ = await _ingest_trace(client, api_key)
    body = {"trace_id": trace_id, "name": "thumbs", "value": 1, "external_id": "fb-1"}
    first = await client.post("/v1/scores", json=body, headers=key_auth(api_key))
    assert first.status_code == 201, first.text
    second = await client.post(
        "/v1/scores", json={**body, "value": 0, "comment": "changed my mind"},
        headers=key_auth(api_key),
    )
    assert second.json()["id"] == first.json()["id"] and second.json()["value"] == 0

    missing = await client.post(
        "/v1/scores",
        json={"trace_id": uuid.uuid4().hex, "name": "thumbs", "value": 1},
        headers=key_auth(api_key),
    )
    assert missing.status_code == 404


async def test_human_annotation_filter_and_delete(user_client, project, api_key):
    client, headers, user = user_client
    await _ingest_trace(client, api_key, name="good")
    await _ingest_trace(client, api_key, name="bad")
    listing = (await client.get(f"/api/projects/{project['id']}/traces", headers=headers)).json()
    by_name = {t["name"]: t for t in listing["items"]}

    for name, value in (("good", 0.9), ("bad", 0.2)):
        created = await client.post(
            f"/api/traces/{by_name[name]['id']}/scores",
            json={"name": "quality", "value": value, "comment": "reviewed"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["source"] == "human" and created.json()["author_id"] == user["id"]

    low = await client.get(
        f"/api/projects/{project['id']}/traces",
        params={"score_name": "quality", "score_max": 0.5},
        headers=headers,
    )
    assert [t["name"] for t in low.json()["items"]] == ["bad"]

    score_id = created.json()["id"]
    assert (await client.delete(f"/api/scores/{score_id}", headers=headers)).status_code == 204
    remaining = await client.get(f"/api/traces/{by_name['bad']['id']}/scores", headers=headers)
    assert remaining.json() == []


async def test_score_type_validation(user_client, project, api_key):
    client, headers, _ = user_client
    await _ingest_trace(client, api_key)
    trace = await _trace(client, headers, project)
    bad = await client.post(
        f"/api/traces/{trace['id']}/scores",
        json={"name": "quality", "value": "great", "data_type": "numeric"},
        headers=headers,
    )
    assert bad.status_code == 422


async def test_score_summary(user_client, project, api_key):
    client, headers, _ = user_client
    trace_id, _ = await _ingest_trace(client, api_key)
    for value in (0.5, 1.0):
        await client.post(
            "/v1/scores",
            json={"trace_id": trace_id, "name": "accuracy", "value": value},
            headers=key_auth(api_key),
        )
    for label in ("friendly", "friendly", "curt"):
        await client.post(
            "/v1/scores",
            json={"trace_id": trace_id, "name": "tone", "value": label},
            headers=key_auth(api_key),
        )
    summary = (
        await client.get(f"/api/projects/{project['id']}/scores/summary", headers=headers)
    ).json()
    by_name = {s["name"]: s for s in summary}
    assert by_name["accuracy"]["count"] == 2 and by_name["accuracy"]["mean"] == 0.75
    assert by_name["tone"]["distribution"] == {"friendly": 2, "curt": 1}
    assert sum(p["count"] for p in by_name["accuracy"]["series"]) == 2


async def test_scores_are_isolated_between_users(user_client, project, api_key, client):
    owner_client, headers, _ = user_client
    await _ingest_trace(owner_client, api_key)
    trace = await _trace(owner_client, headers, project)
    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "name": "Other", "password": "sup3r-secret-pw"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    response = await client.get(f"/api/traces/{trace['id']}/scores", headers=other_headers)
    assert response.status_code == 404
    response = await client.post(
        f"/api/traces/{trace['id']}/scores",
        json={"name": "quality", "value": 1},
        headers=other_headers,
    )
    assert response.status_code == 404


async def test_score_configs(user_client, project):
    client, headers, _ = user_client
    url = f"/api/projects/{project['id']}/score-configs"
    bad = await client.put(url, json={"name": "tone", "data_type": "categorical"}, headers=headers)
    assert bad.status_code == 422
    ok = await client.put(
        url,
        json={"name": "tone", "data_type": "categorical", "categories": ["friendly", "curt"]},
        headers=headers,
    )
    assert ok.status_code == 200
    assert [c["name"] for c in (await client.get(url, headers=headers)).json()] == ["tone"]
