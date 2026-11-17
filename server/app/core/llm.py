"""Provider-agnostic single model call.

Shared by replay, LLM judges, prompt experiments and the playground.

Providers
---------
* "simulation": deterministic offline mock, always available (demo mode, tests).
* "anthropic":  official Anthropic SDK, using the project's stored key.
* "openai":     OpenAI-compatible chat completions over HTTPS.

A call never executes tools: tool definitions are forwarded so the model can
*request* a call, and requested calls are returned in `output["tool_calls"]`.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models import ProviderCredential

DEFAULT_MAX_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 120.0
PROVIDERS = ("simulation", "anthropic", "openai")

# (api_key, base_url) per provider name.
Credentials = dict[str, tuple[str, str | None]]


class LLMConfigError(Exception):
    """The call cannot be made as configured (missing key, unknown provider).

    User-facing; provider/network failures surface as ordinary exceptions.
    """


@dataclass
class LLMRequest:
    provider: str
    model: str
    messages: list[dict[str, Any]]
    system: str | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    params: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] | None = None
    # When set, the response text is JSON conforming to this schema.
    json_schema: dict[str, Any] | None = None


@dataclass
class LLMResult:
    output: dict[str, Any]
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None

    @property
    def text(self) -> str:
        content = self.output.get("content")
        return content if isinstance(content, str) else ""

    def json(self) -> Any:
        return json.loads(self.text)


def parse_llm_input(raw: Any, system: str | None = None) -> tuple[list[dict], str | None]:
    """Recorded LLM input → (messages, system).

    Accepts `{"messages": [...], "system": "..."}`, a bare message list,
    `{"prompt": "..."}` or a plain string. Raises ValueError otherwise.
    """
    if isinstance(raw, dict):
        if system is None and isinstance(raw.get("system"), str):
            system = raw["system"]
        if isinstance(raw.get("messages"), list):
            return _split_system(raw["messages"], system)
        if isinstance(raw.get("prompt"), str):
            return [{"role": "user", "content": raw["prompt"]}], system
    elif isinstance(raw, list):
        return _split_system(raw, system)
    elif isinstance(raw, str):
        return [{"role": "user", "content": raw}], system
    raise ValueError("Not a recognisable model input")


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


async def load_credentials(db: AsyncSession, project_id: Any) -> Credentials:
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.project_id == project_id)
    )
    creds: Credentials = {}
    for cred in result.scalars():
        key = decrypt_secret(cred.encrypted_key)
        if key is not None:
            creds[cred.provider] = (key, cred.base_url)
    return creds


def infer_provider(model: str, creds: Credentials) -> str:
    lowered = model.lower()
    if lowered.startswith("claude") and "anthropic" in creds:
        return "anthropic"
    if (lowered.startswith(("gpt", "o1", "o3", "o4")) or "/" in lowered) and "openai" in creds:
        return "openai"
    return "simulation"


async def complete(request: LLMRequest, creds: Credentials) -> LLMResult:
    if request.provider == "simulation":
        return await _run_simulation(request)
    if request.provider == "anthropic":
        if "anthropic" not in creds:
            raise LLMConfigError(
                "No Anthropic API key configured for this project "
                "(Settings → Replay credentials)"
            )
        return await _run_anthropic(creds["anthropic"], request)
    if request.provider == "openai":
        if "openai" not in creds:
            raise LLMConfigError(
                "No OpenAI-compatible API key configured for this project "
                "(Settings → Replay credentials)"
            )
        return await _run_openai(creds["openai"], request)
    raise LLMConfigError(f"Unknown provider: {request.provider}")


# ------------------------------------------------------------------ simulation


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(block))
        return " ".join(p for p in parts if p)
    return "" if content is None else str(content)


def simulate_json(schema: dict[str, Any], seed: str) -> Any:
    """Deterministic value conforming to (a practical subset of) a JSON schema."""
    kind = schema.get("type")
    if "enum" in schema:
        options = schema["enum"]
        return options[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(options)]
    if kind == "object":
        return {
            key: simulate_json(sub, f"{seed}.{key}")
            for key, sub in (schema.get("properties") or {}).items()
        }
    if kind == "array":
        return [simulate_json(schema.get("items") or {}, f"{seed}[0]")]
    if kind in ("number", "integer"):
        low = schema.get("minimum", 0)
        high = schema.get("maximum", 1)
        fraction = (int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % 1000) / 999
        value = low + (high - low) * fraction
        return round(value) if kind == "integer" else round(value, 3)
    if kind == "boolean":
        return int(hashlib.sha256(seed.encode()).hexdigest()[:2], 16) % 2 == 0
    return f"simulated:{hashlib.sha256(seed.encode()).hexdigest()[:8]}"


async def _run_simulation(request: LLMRequest) -> LLMResult:
    """Deterministic offline provider so every workflow is usable without keys."""
    corpus = " ".join(_content_text(m.get("content")) for m in request.messages)
    digest = hashlib.sha256(((request.system or "") + corpus).encode()).hexdigest()[:8]
    await asyncio.sleep(0.15 if request.json_schema is None else 0)  # feel like a model call
    if request.json_schema is not None:
        text = json.dumps(simulate_json(request.json_schema, digest))
    else:
        last_user = next(
            (
                _content_text(m.get("content"))
                for m in reversed(request.messages)
                if m.get("role") == "user"
            ),
            "",
        )
        text = (
            f"[simulated:{digest}] Replayed with model {request.model}. "
            f"In response to: {last_user[:280]!r} — this deterministic output stands in "
            "for a live model call. Configure a provider API key in project settings "
            "to replay against the real model."
        )
    return LLMResult(
        output={"role": "assistant", "content": text, "simulated": True},
        input_tokens=max(1, len(corpus) // 4),
        output_tokens=max(1, len(text) // 4),
    )


# ------------------------------------------------------------------- anthropic


async def _run_anthropic(cred: tuple[str, str | None], request: LLMRequest) -> LLMResult:
    from anthropic import AsyncAnthropic

    api_key, base_url = cred
    client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": REQUEST_TIMEOUT_SECONDS}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = AsyncAnthropic(**client_kwargs)

    body: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        # Content is forwarded as recorded: a string, or a list of content
        # blocks (text / tool_use / tool_result / image).
        "messages": [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in request.messages
            if m.get("role") in ("user", "assistant")
        ],
    }
    if request.system:
        body["system"] = request.system
    if request.tools:
        body["tools"] = request.tools
    if request.json_schema is not None:
        body["output_config"] = {
            "format": {"type": "json_schema", "schema": request.json_schema}
        }
    # Sampling parameters (temperature/top_p/top_k) are rejected by current
    # Claude models, so they are intentionally not forwarded.

    response = await client.messages.create(**body)
    usage = response.usage
    output: dict[str, Any] = {"role": "assistant", "stop_reason": response.stop_reason}
    if response.stop_reason == "refusal":
        output["content"] = ""
    else:
        output["content"] = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in response.content
            if b.type == "tool_use"
        ]
        if tool_calls:
            output["tool_calls"] = tool_calls
    return LLMResult(
        output=output,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", None),
    )


# ---------------------------------------------------------------------- openai


async def _run_openai(cred: tuple[str, str | None], request: LLMRequest) -> LLMResult:
    api_key, base_url = cred
    url = (base_url or "https://api.openai.com").rstrip("/") + "/v1/chat/completions"
    messages = list(request.messages)
    if request.system:
        messages = [{"role": "system", "content": request.system}, *messages]
    body: dict[str, Any] = {
        "model": request.model,
        "messages": messages,
        "max_tokens": request.max_tokens,
    }
    for key in ("temperature", "top_p"):
        if key in request.params:
            body[key] = request.params[key]
    if request.tools:
        body["tools"] = request.tools
    if request.json_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": request.json_schema, "strict": True},
        }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url, json=body, headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        data = response.json()
    choice = (data.get("choices") or [{}])[0]
    usage = data.get("usage") or {}
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    prompt_tokens = usage.get("prompt_tokens")
    if prompt_tokens is not None and cached:
        prompt_tokens -= cached  # keep `input_tokens` = uncached input
    return LLMResult(
        output=choice.get("message", {"role": "assistant", "content": ""}),
        input_tokens=prompt_tokens,
        output_tokens=usage.get("completion_tokens"),
        cache_read_tokens=cached or None,
    )
