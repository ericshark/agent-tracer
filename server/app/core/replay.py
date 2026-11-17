"""Replay engine: re-run a recorded LLM span with its original or edited input.

Safety model
------------
* A replay executes exactly one model call — never tools, never side effects.
* Results are stored as separate Replay rows; the original trace is immutable.
* The model call itself goes through app.core.llm (simulation / anthropic / openai).
"""

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import (
    DEFAULT_MAX_TOKENS,
    LLMConfigError,
    LLMRequest,
    complete,
    infer_provider,
    load_credentials,
)
from app.core.pricing import estimate_cost
from app.models import Replay, Span, User
from app.schemas.replay import ReplayCreate


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
    extra_params = {k: v for k, v in params.items() if k != "max_tokens"}

    creds = await load_credentials(db, span.project_id)
    provider = payload.provider or infer_provider(model, creds)

    replay_input = {
        "messages": messages,
        "system": system,
        "model": model,
        "params": {"max_tokens": max_tokens, **extra_params},
    }
    if payload.tools:
        replay_input["tools"] = payload.tools

    started = time.perf_counter()
    status_val, output, error_message = "ok", None, None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    try:
        result = await complete(
            LLMRequest(
                provider=provider,
                model=model,
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                params=extra_params,
                tools=payload.tools,
            ),
            creds,
        )
        output = result.output
        input_tokens, output_tokens = result.input_tokens, result.output_tokens
        if provider != "simulation":
            cost = estimate_cost(
                model,
                input_tokens,
                output_tokens,
                result.cache_read_tokens,
                result.cache_creation_tokens,
            )
    except LLMConfigError as exc:
        raise ReplayError(str(exc)) from exc
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
        cost_usd=cost,
    )
    db.add(replay)
    await db.commit()
    await db.refresh(replay)
    return replay
