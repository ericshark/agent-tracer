from httpx import AsyncClient


async def test_register_login_me_flow(client: AsyncClient):
    register = await client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "name": "Alice", "password": "password123"},
    )
    assert register.status_code == 201
    body = register.json()
    assert body["user"]["email"] == "alice@example.com"
    assert "access_token" in body

    login = await client.post(
        "/api/auth/login",
        json={"email": "Alice@Example.com", "password": "password123"},
    )
    assert login.status_code == 200

    token = login.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Alice"


async def test_register_duplicate_email_conflict(client: AsyncClient):
    payload = {"email": "bob@example.com", "name": "Bob", "password": "password123"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    assert (await client.post("/api/auth/register", json=payload)).status_code == 409


async def test_login_wrong_password_rejected(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={"email": "carol@example.com", "name": "Carol", "password": "password123"},
    )
    bad = await client.post(
        "/api/auth/login", json={"email": "carol@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401


async def test_short_password_rejected(client: AsyncClient):
    response = await client.post(
        "/api/auth/register",
        json={"email": "dan@example.com", "name": "Dan", "password": "short"},
    )
    assert response.status_code == 422


async def test_me_requires_auth(client: AsyncClient):
    assert (await client.get("/api/auth/me")).status_code == 401
    bad = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


async def test_auth_rate_limit(client: AsyncClient):
    payload = {"email": "eve@example.com", "password": "whatever-pw"}
    statuses = set()
    for _ in range(25):
        response = await client.post("/api/auth/login", json=payload)
        statuses.add(response.status_code)
    assert 429 in statuses


async def test_health_endpoints(client: AsyncClient):
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).json() == {"status": "ready"}
