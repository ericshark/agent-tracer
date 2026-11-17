import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_ITEM_BYTES = 256 * 1024
MAX_ITEMS_PER_REQUEST = 5000


def _check_size(value: Any) -> Any:
    # Test cases are stored verbatim: reject oversized values instead of truncating.
    if value is not None and len(json.dumps(value, default=str)) > MAX_ITEM_BYTES:
        raise ValueError(f"Value exceeds {MAX_ITEM_BYTES // 1024} KiB")
    return value


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class DatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    item_count: int = 0


class DatasetItemIn(BaseModel):
    input: Any = None
    expected_output: Any = None
    metadata: dict[str, Any] | None = None

    _size = field_validator("input", "expected_output", "metadata")(_check_size)


class DatasetItemsCreate(BaseModel):
    items: list[DatasetItemIn] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class DatasetItemUpdate(BaseModel):
    input: Any = None
    expected_output: Any = None
    metadata: dict[str, Any] | None = None
    archived: bool | None = None

    _size = field_validator("input", "expected_output", "metadata")(_check_size)


class DatasetItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    input: Any
    expected_output: Any
    meta: dict | None = None
    source_trace_pk: uuid.UUID | None
    source_span_pk: uuid.UUID | None
    archived_at: datetime | None
    created_at: datetime


class DatasetItemList(BaseModel):
    items: list[DatasetItemOut]
    total: int
    limit: int
    offset: int


class TraceSource(BaseModel):
    trace_pk: uuid.UUID
    # Omitted → the trace's root span.
    span_pk: uuid.UUID | None = None


class ItemsFromTraces(BaseModel):
    """Capture recorded runs as test cases: the span's input becomes the case
    input and its output the expected output (editable afterwards)."""

    sources: list[TraceSource] = Field(min_length=1, max_length=500)


class DatasetImport(BaseModel):
    format: Literal["jsonl", "csv"]
    content: str = Field(max_length=10 * 1024 * 1024)


class DatasetWithItems(DatasetOut):
    items: list[DatasetItemOut] = Field(default_factory=list)
