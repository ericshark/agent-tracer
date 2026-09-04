import os
import uuid

# Configure the app before it is imported.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from app.api.deps import auth_rate_limiter
from app.db import set_engine_for_testing
from app.main import app
from app.models import Base
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")


@pytest.fixture
async def engine():
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine = create_async_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    set_engine_for_testing(engine)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(engine):
    auth_rate_limiter.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def user_client(client: AsyncClient):
    """Client with a registered user; returns (client, auth headers, user dict)."""
    email = f"dev-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "name": "Dev User", "password": "sup3r-secret-pw"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return client, headers, data["user"]


@pytest.fixture
async def project(user_client):
    client, headers, _user = user_client
    response = await client.post(
        "/api/projects", json={"name": "Test Project"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def api_key(user_client, project):
    client, headers, _user = user_client
    response = await client.post(
        f"/api/projects/{project['id']}/api-keys",
        json={"name": "test key"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["key"]


def make_span(
    trace_id: str | None = None,
    span_id: str | None = None,
    parent: str | None = None,
    **overrides,
) -> dict:
    span = {
        "trace_id": trace_id or uuid.uuid4().hex,
        "span_id": (span_id or uuid.uuid4().hex[:16]),
        "parent_span_id": parent,
        "name": overrides.pop("name", "test-span"),
        "kind": overrides.pop("kind", "AGENT"),
        "status": overrides.pop("status", "ok"),
        "started_at": overrides.pop("started_at", "2026-08-04T12:00:00+00:00"),
        "ended_at": overrides.pop("ended_at", "2026-08-04T12:00:01+00:00"),
    }
    span.update(overrides)
    return span
