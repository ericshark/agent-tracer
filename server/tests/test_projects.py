async def test_project_crud(user_client):
    client, headers, _user = user_client

    created = await client.post(
        "/api/projects",
        json={"name": "My Agent", "description": "test project"},
        headers=headers,
    )
    assert created.status_code == 201
    project = created.json()

    listed = await client.get("/api/projects", headers=headers)
    assert [p["id"] for p in listed.json()] == [project["id"]]

    patched = await client.patch(
        f"/api/projects/{project['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert patched.json()["name"] == "Renamed"

    deleted = await client.delete(f"/api/projects/{project['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/projects", headers=headers)).json() == []


async def test_projects_are_owner_scoped(user_client, project):
    client, _headers, _user = user_client
    other = await client.post(
        "/api/auth/register",
        json={"email": "intruder@example.com", "name": "Intruder", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    response = await client.get(f"/api/projects/{project['id']}", headers=other_headers)
    assert response.status_code == 404


async def test_api_key_lifecycle(user_client, project):
    client, headers, _user = user_client
    base = f"/api/projects/{project['id']}/api-keys"

    created = await client.post(base, json={"name": "ci key"}, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("at_")
    assert len(body["key"]) == 51
    assert body["key_prefix"] == body["key"][:10]

    listed = await client.get(base, headers=headers)
    assert len(listed.json()) == 1
    assert "key" not in listed.json()[0]  # plaintext never returned again

    revoked = await client.delete(f"{base}/{body['id']}", headers=headers)
    assert revoked.json()["revoked_at"] is not None


async def test_revoked_key_rejected_for_ingest(user_client, project, api_key):
    client, headers, _user = user_client
    keys = (
        await client.get(f"/api/projects/{project['id']}/api-keys", headers=headers)
    ).json()
    await client.delete(
        f"/api/projects/{project['id']}/api-keys/{keys[0]['id']}", headers=headers
    )
    response = await client.post(
        "/v1/ingest",
        json={"spans": []},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 401


async def test_credentials_masked(user_client, project):
    client, headers, _user = user_client
    base = f"/api/projects/{project['id']}/credentials"

    put = await client.put(
        base,
        json={"provider": "anthropic", "api_key": "sk-ant-super-secret-key-123456"},
        headers=headers,
    )
    assert put.status_code == 200
    assert "super-secret" not in put.json()["masked_key"]

    listed = await client.get(base, headers=headers)
    assert listed.json()[0]["provider"] == "anthropic"
    assert "super-secret" not in listed.json()[0]["masked_key"]

    assert (
        await client.delete(f"{base}/anthropic", headers=headers)
    ).status_code == 204
