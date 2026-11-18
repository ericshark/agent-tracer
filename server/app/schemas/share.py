import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShareCreate(BaseModel):
    expires_in_hours: int = Field(default=168, ge=1, le=720)


class ShareLookup(BaseModel):
    token: str = Field(min_length=40, max_length=128)


class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    token: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class PublicTraceOut(BaseModel):
    """Aggregate metrics safe to share without publishing trace content."""

    duration_ms: float | None
    span_count: int
    error_count: int
    llm_call_count: int
    input_tokens: int
    output_tokens: int
