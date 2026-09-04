"""Replay engine: re-run a recorded LLM span with its original or edited input.

Safety model
------------
* A replay executes exactly one model call — never tools, never side effects.
* Results are stored as separate Replay rows; the original trace is immutable.
* Providers:
    - "simulation": deterministic offline mock, always available (demo mode).
    - "anthropic":  official Anthropic SDK, using the project's stored key.
    - "openai":     OpenAI-compatible chat completions over HTTPS.
"""

import asyncio
import hashlib
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pricing import estimate_cost
from app.core.security import decrypt_secret
from app.models import ProviderCredential, Replay, Span, User
from app.schemas.replay import ReplayCreate

DEFAULT_MAX_TOKENS = 4096
_REPLAY_TIMEOUT_SECONDS = 120.0


class ReplayError(Exception):
    """User-facing replay validation error (mapped to HTTP 400)."""


def extract_llm_input(span: Span, payload: ReplayCreate) -> tuple[list[dict], str | None]:
    """Resolve the message list and system prompt for the replay."""
    if payload.messages is not None:
        return payload.messages, payload.system

    system = payload.system
    raw = span.input
    if isinstance(raw, dict):
        messages = raw.get("messages")
        if system is None and isinstance(raw.get("system"), str):
            system = raw["system"]
        if isinstance(messages, list):
            return _split_system(messages, system)
        prompt = raw.get("prompt")
        if isinstance(prompt, str):
            return [{"role": "user", "content": prompt}], system
    elif isinstance(raw, list):
        return _split_system(raw, system)
    elif isinstance(raw, str):
        return [{"role": "user", "content": raw}], system
    raise ReplayError(
        "This span has no replayable input. Provide `messages` explicitly to replay it."
    )


def _split_system(messages: list[Any], system: str | None) -> tuple[list[dict], str | None]:
    out: list[dict] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "system" and system is None and isinstance(m.get("content"), str):
            system = m["content"]
            continue
        out.append(m)
    return out, system


async def _load_credential(
    db: AsyncSession, project_id: Any, provider: str
) -> tuple[str, str | None] | None:
    result = await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.project_id == project_id,
            ProviderCredential.provider == provider,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        return None
    key = decrypt_secret(cred.encrypted_key)
    if key is None:
        return None
    return key, cred.base_url


def _infer_provider(model: str, has_anthropic: bool, has_openai: bool) -> str:
    lowered = model.lower()
    if lowered.startswith("claude") and has_anthropic:
        return "anthropic"
    if (lowered.startswith(("gpt", "o1", "o3", "o4")) or "/" in lowered) and has_openai:
        return "openai"
    return "simulation"


async def execute_replay(
    db: AsyncSession, user: User, span: Span, payload: ReplayCreate
) -> Replay:
    if span.kind != "LLM":
        raise ReplayError("Only LLM spans can be replayed")

    messages, system = extract_llm_input(span, payload)
    if not messages:
        raise ReplayError("Replay requires at least one message")
    model = payload.model or span.model
    if not model:
        raise ReplayError("This span records no model — pass `model` explicitly")

    params = dict(payload.params or {})
    max_tokens = int(params.get("max_tokens", DEFAULT_MAX_TOKENS))

    anthropic_cred = await _load_credential(db, span.project_id, "anthropic")
    openai_cred = await _load_credential(db, span.project_id, "openai")
    provider = payload.provider or _infer_provider(
        model, anthropic_cred is not None, openai_cred is not None
    )

    extra_params = {k: v for k, v in params.items() if k != "max_tokens"}
    replay_input = {
        "messages": messages,
        "system": system,
        "model": model,
        "params": {"max_tokens": max_tokens, **extra_params},
    }

    started = time.perf_counter()
    status_val, output, error_message = "ok", None, None
    input_tokens: int | None = None
    output_tokens: int | None = None
    try:
        if provider == "simulation":
            output, input_tokens, output_tokens = await _run_simulation(
                model, messages, system
            )
        elif provider == "anthropic":
            if anthropic_cred is None:
                raise ReplayError(
                    "No Anthropic API key configured for this project "
                    "(Settings → Replay credentials)"
                )
            output, input_tokens, output_tokens = await _run_anthropic(
                anthropic_cred, model, messages, system, max_tokens
            )
        elif provider == "openai":
            if openai_cred is None:
                raise ReplayError(
                    "No OpenAI-compatible API key configured for this project "
                    "(Settings → Replay credentials)"
                )
            output, input_tokens, output_tokens = await _run_openai(
                openai_cred, model, messages, system, max_tokens, params
            )
        else:
            raise ReplayError(f"Unknown provider: {provider}")
    except ReplayError:
        raise
    except Exception as exc:  # provider/network failure — recorded, not raised
        status_val = "error"
        error_message = f"{type(exc).__name__}: {exc}"[:4000]

    latency_ms = (time.perf_counter() - started) * 1000.0
    replay = Replay(
        span_pk=span.id,
        project_id=span.project_id,
        created_by=user.id,
        provider=provider,
        model=model,
        input=replay_input,
        output=output,
        status=status_val,
        error_message=error_message,
        latency_ms=round(latency_ms, 3),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=None if provider == "simulation" else estimate_cost(
            model, input_tokens, output_tokens
        ),
    )
    db.add(replay)
    await db.commit()
    await db.refresh(replay)
    return replay


# ------------------------------------------------------------------ providers


async def _run_simulation(
    model: str, messages: list[dict], system: str | None
) -> tuple[dict, int, int]:
    """Deterministic offline provider so replay is demonstrable without keys."""
    corpus = " ".join(str(m.get("content", "")) for m in messages)
    digest = hashlib.sha256(((system or "") + corpus).encode()).hexdigest()[:8]
    await asyncio.sleep(0.15)  # feel like a model call, stay test-fast
    last_user = next(
        (str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    text = (
        f"[simulated:{digest}] Replayed with model {model}. "
        f"In response to: {last_user[:280]!r} — this deterministic output stands in "
        "for a live model call. Configure a provider API key in project settings "
        "to replay against the real model."
    )
    input_tokens = max(1, len(corpus) // 4)
    output_tokens = max(1, len(text) // 4)
    return (
        {"role": "assistant", "content": text, "simulated": True},
        input_tokens,
        output_tokens,
    )


async def _run_anthropic(
    cred: tuple[str, str | None],
    model: str,
    messages: list[dict],
    system: str | None,
    max_tokens: int,
) -> tuple[dict, int | None, int | None]:
    from anthropic import AsyncAnthropic

    api_key, base_url = cred
    client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": _REPLAY_TIMEOUT_SECONDS}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = AsyncAnthropic(**client_kwargs)

    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ],
    }
    if system:
        request["system"] = system

    response = await client.messages.create(**request)
    if response.stop_reason == "refusal":
        return (
            {"role": "assistant", "content": "", "stop_reason": "refusal"},
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
    text = "".join(block.text for block in response.content if block.type == "text")
    return (
        {"role": "assistant", "content": text, "stop_reason": response.stop_reason},
        response.usage.input_tokens,
        response.usage.output_tokens,
    )


async def _run_openai(
    cred: tuple[str, str | None],
    model: str,
    messages: list[dict],
    system: str | None,
    max_tokens: int,
    params: dict[str, Any],
) -> tuple[dict, int | None, int | None]:
    api_key, base_url = cred
    url = (base_url or "https://api.openai.com").rstrip("/") + "/v1/chat/completions"
    request_messages = list(messages)
    if system:
        request_messages = [{"role": "system", "content": system}, *request_messages]
    body: dict[str, Any] = {
        "model": model,
        "messages": request_messages,
        "max_tokens": max_tokens,
    }
    if "temperature" in params:
        body["temperature"] = params["temperature"]

    async with httpx.AsyncClient(timeout=_REPLAY_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url, json=body, headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        data = response.json()
    choice = (data.get("choices") or [{}])[0]
    usage = data.get("usage") or {}
    return (
        choice.get("message", {"role": "assistant", "content": ""}),
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
    )
