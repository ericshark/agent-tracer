import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TraceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_id: str
    name: str
    status: str
    session_id: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_ms: float | None
    span_count: int
    error_count: int
    llm_call_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    meta: dict | None = None


class SpanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: float | None
    input: Any
    output: Any
    attributes: dict | None
    events: list | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    error_type: str | None
    error_message: str | None
    error_stacktrace: str | None


class TraceDetail(TraceSummary):
    spans: list[SpanOut]


class TraceListResponse(BaseModel):
    items: list[TraceSummary]
    total: int
    limit: int
    offset: int


class StatsBucket(BaseModel):
    bucket_start: datetime
    trace_count: int
    error_count: int
    avg_duration_ms: float | None
    total_tokens: int
    cost_usd: float


class ProjectStats(BaseModel):
    window_hours: int
    trace_count: int
    error_count: int
    error_rate: float
    avg_duration_ms: float | None
    p95_duration_ms: float | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    buckets: list[StatsBucket]
