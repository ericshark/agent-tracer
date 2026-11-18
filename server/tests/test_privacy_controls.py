import logging
import uuid
from datetime import timedelta

from app.config import get_settings
from app.core.retention import expire_traces
from app.db import get_session_factory
from app.models import BrowserSession, Trace, utcnow
from sqlalchemy import select

from tests.conftest import make_span, session_headers


async def test_rejects_cross_origin_writes_and_revokes_session(user_client, project):
    client, headers, _ = user_client
    cross_origin = dict(headers, Origin="https://different-origin.example")
    assert (
        await client.delete(f"/api/projects/{project['id']}", headers=cross_origin)
    ).status_code == 403
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


async def test_account_deletion_confirmed_and_cascades(user_client, project, api_key):
    client, headers, user = user_client
    path = "/api/auth/me"
    response = await client.request("DELETE", path, headers=headers, json={"password": "wrong"})
    assert response.status_code == 403
    response = await client.request(
        "DELETE", path, headers=headers, json={"password": "sup3r-secret-pw"}
    )
    assert response.status_code == 204
    assert (await client.get(path, headers=headers)).status_code == 401
    async with get_session_factory()() as db:
        assert (
            await db.scalar(
                select(BrowserSession).where(BrowserSession.user_id == uuid.UUID(user["id"]))
            )
            is None
        )
    key_headers = {"Authorization": f"Bearer {api_key}"}
    assert (
        await client.post("/v1/ingest", json={"spans": []}, headers=key_headers)
    ).status_code == 401


async def test_provider_policy_applies_per_provider(user_client, project, monkeypatch):
    client, headers, _ = user_client
    monkeypatch.setattr(get_settings(), "openai_provider_hosts", "approved.example")
    path = f"/api/projects/{project['id']}/credentials"

    async def put(host, provider):
        return await client.put(
            path,
            headers=headers,
            json={
                "api_key": "synthetic-test-key",
                "provider": provider,
                "base_url": host,
            },
        )

    assert (await put("https://approved.example/model", "openai")).status_code == 200
    assert (await put("https://approved.example/model", "anthropic")).status_code == 422
    assert (await put("http://approved.example", "openai")).status_code == 422


async def test_retention_grace_and_public_share_cleanup(
    user_client, project, api_key, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="agent_tracer")
    client, headers, _ = user_client
    now = utcnow()
    span = make_span(
        started_at=(now - timedelta(days=31)).isoformat(),
        ended_at=(now - timedelta(days=31) + timedelta(seconds=1)).isoformat(),
    )
    response = await client.post(
        "/v1/ingest", json={"spans": [span]}, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert response.status_code == 200
    async with get_session_factory()() as db:
        trace = await db.scalar(select(Trace))
        trace_pk = trace.id
    share = await client.post(f"/api/traces/{trace_pk}/shares", headers=headers)
    token = share.json()["token"]
    public = f"/api/share/{token}"
    assert (await client.get(public)).status_code == 200
    assert token not in caplog.text

    monkeypatch.setattr(get_settings(), "trace_retention_enabled_at", now)
    assert await expire_traces(now + timedelta(days=29)) == 0
    assert await expire_traces(now + timedelta(days=30)) == 1
    assert (await client.get(public)).status_code == 404


async def test_expired_session_is_rejected(client):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "expiry@example.com",
            "name": "Session expiry",
            "password": "password123",
        },
    )
    async with get_session_factory()() as db:
        session = await db.scalar(select(BrowserSession))
        session.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()
    assert (await client.get("/api/auth/me", headers=session_headers(response))).status_code == 401


async def test_anthropic_uses_sdk_transport_without_redirects(monkeypatch):
    from importlib import import_module

    import anthropic
    from app.core.llm import LLMRequest, _run_anthropic

    real_client = anthropic.DefaultAsyncHttpxClient
    transport_module = import_module(real_client.__mro__[1].__module__.split(".")[0])

    def respond(request):
        assert request.url.host == "api.anthropic.com"
        return transport_module.Response(
            200,
            json={
                "id": "msg_synthetic",
                "type": "message",
                "role": "assistant",
                "model": "synthetic-model",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Synthetic response"}],
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        )

    def client(**options):
        assert options["follow_redirects"] is False
        assert options["trust_env"] is False
        return real_client(**options, transport=transport_module.MockTransport(respond))

    monkeypatch.setattr(anthropic, "DefaultAsyncHttpxClient", client)
    result = await _run_anthropic(
        ("synthetic-model-key", None),
        LLMRequest("anthropic", "synthetic-model", [{"role": "user", "content": "Test"}]),
    )
    assert result.text == "Synthetic response"
