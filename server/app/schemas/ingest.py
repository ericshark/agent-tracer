from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SPAN_KINDS = {"AGENT", "LLM", "TOOL", "CHAIN", "RETRIEVER", "EMBEDDING", "GUARDRAIL", "UNKNOWN"}

# Guardrail so a single pathological span cannot blow up storage.
MAX_VALUE_BYTES = 256 * 1024


def _truncate_json_value(value: Any) -> Any:
    """Truncate oversized payload values while keeping them valid JSON."""
    if value is None:
        return None
    import json

    try:
        encoded = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return {"_truncated": True, "preview": str(value)[:1000]}
    if len(encoded) <= MAX_VALUE_BYTES:
        return value
    return {"_truncated": True, "preview": encoded[:MAX_VALUE_BYTES]}


class SpanErrorIn(BaseModel):
    type: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=8192)
    stacktrace: str | None = Field(default=None, max_length=32768)


class SpanIn(BaseModel):
    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    span_id: str = Field(pattern="^[0-9a-f]{16}$")
    parent_span_id: str | None = Field(default=None, pattern="^[0-9a-f]{16}$")
    name: str = Field(min_length=1, max_length=255)
    kind: str = "UNKNOWN"
    status: Literal["running", "ok", "error"] = "running"
    started_at: datetime
    ended_at: datetime | None = None
    input: Any = None
    output: Any = None
    attributes: dict[str, Any] | None = None
    events: list[dict[str, Any]] | None = None
    model: str | None = Field(default=None, max_length=128)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    error: SpanErrorIn | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: Any) -> str:
        kind = str(v or "UNKNOWN").upper()
        return kind if kind in SPAN_KINDS else "UNKNOWN"

    @field_validator("input", "output", mode="before")
    @classmethod
    def cap_payloads(cls, v: Any) -> Any:
        return _truncate_json_value(v)

    @field_validator("attributes", "events", mode="before")
    @classmethod
    def cap_meta(cls, v: Any) -> Any:
        capped = _truncate_json_value(v)
        # If truncation replaced the container with a marker dict, keep shape valid.
        if isinstance(v, list) and isinstance(capped, dict):
            return [capped]
        return capped


class TraceIn(BaseModel):
    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    name: str | None = Field(default=None, max_length=255)
    status: Literal["running", "ok", "error"] | None = None
    session_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def cap_metadata(cls, v: Any) -> Any:
        return _truncate_json_value(v)


class IngestRequest(BaseModel):
    traces: list[TraceIn] = Field(default_factory=list)
    spans: list[SpanIn] = Field(default_factory=list)


class IngestResponse(BaseModel):
    accepted_traces: int
    accepted_spans: int
