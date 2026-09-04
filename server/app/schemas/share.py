import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.traces import SpanOut, TraceSummary


class ShareCreate(BaseModel):
    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 90)


class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    token: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class PublicTraceOut(BaseModel):
    """Read-only trace view returned for a share token. No project/user data."""

    trace: TraceSummary
    spans: list[SpanOut]
    project_name: str
