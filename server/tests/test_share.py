import uuid

from tests.conftest import make_span


async def ingest_trace(client, api_key: str) -> None:
    trace_id = uuid.uuid4().hex
    spans = [
        make_span(trace_id, "aa" * 8, name="shared-run", kind="AGENT"),
        make_span(trace_id, "bb" * 8, parent="aa" * 8, name="step", kind="TOOL"),
    ]
    response = await client.post(
        "/v1/ingest", json={"spans": spans}, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert response.status_code == 200


async def test_share_link_lifecycle(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_trace(client, api_key)
    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace_pk = listed.json()["items"][0]["id"]

    created = await client.post(
        f"/api/traces/{trace_pk}/shares", json={}, headers=headers
    )
    assert created.status_code == 201
    share = created.json()
    assert len(share["token"]) >= 40

    # Public access without any auth
    public = await client.get(f"/api/share/{share['token']}")
    assert public.status_code == 200
    body = public.json()
    assert body["trace"]["name"] == "shared-run"
    assert len(body["spans"]) == 2
    assert body["project_name"] == "Test Project"

    # Revoke → 404
    revoked = await client.delete(f"/api/shares/{share['id']}", headers=headers)
    assert revoked.json()["revoked_at"] is not None
    assert (await client.get(f"/api/share/{share['token']}")).status_code == 404


async def test_share_link_with_expiry(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_trace(client, api_key)
    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace_pk = listed.json()["items"][0]["id"]

    created = await client.post(
        f"/api/traces/{trace_pk}/shares", json={"expires_in_hours": 24}, headers=headers
    )
    assert created.json()["expires_at"] is not None
    assert (await client.get(f"/api/share/{created.json()['token']}")).status_code == 200


async def test_share_body_is_optional(user_client, project, api_key):
    """POST with no body creates a non-expiring link (curl-friendly)."""
    client, headers, _user = user_client
    await ingest_trace(client, api_key)
    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace_pk = listed.json()["items"][0]["id"]

    created = await client.post(f"/api/traces/{trace_pk}/shares", headers=headers)
    assert created.status_code == 201
    assert created.json()["expires_at"] is None
    assert (await client.get(f"/api/share/{created.json()['token']}")).status_code == 200


async def test_unknown_share_token_404(client):
    assert (await client.get("/api/share/definitely-not-a-token")).status_code == 404


async def test_share_creation_requires_ownership(user_client, project, api_key):
    client, headers, _user = user_client
    await ingest_trace(client, api_key)
    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace_pk = listed.json()["items"][0]["id"]

    other = await client.post(
        "/api/auth/register",
        json={"email": "sneaky@example.com", "name": "Sneaky", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    response = await client.post(
        f"/api/traces/{trace_pk}/shares", json={}, headers=other_headers
    )
    assert response.status_code == 404
