import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReplayCreate(BaseModel):
    """Request to re-run an LLM span with the recorded — or edited — input.

    Every field is optional: by default the replay uses the span's recorded
    provider-agnostic messages, model, and parameters.
    """

    provider: Literal["simulation", "anthropic", "openai"] | None = None
    model: str | None = Field(default=None, max_length=128)
    messages: list[dict[str, Any]] | None = None
    system: str | None = Field(default=None, max_length=32768)
    params: dict[str, Any] | None = None  # e.g. {"max_tokens": 1024}


class ReplayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    span_pk: uuid.UUID
    provider: str
    model: str
    input: dict
    output: dict | None
    status: str
    error_message: str | None
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    created_at: datetime
