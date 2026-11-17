import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScoreDataType = Literal["numeric", "boolean", "categorical"]
ScoreSource = Literal["sdk", "api", "human", "evaluator"]


class ScoreBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # number → numeric, bool → boolean, string → categorical (unless data_type says otherwise)
    value: float | bool | str
    data_type: ScoreDataType | None = None
    comment: str | None = Field(default=None, max_length=8192)
    metadata: dict[str, Any] | None = None
    external_id: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def check_value_matches_type(self) -> "ScoreBase":
        inferred: ScoreDataType = (
            "boolean"
            if isinstance(self.value, bool)
            else "categorical"
            if isinstance(self.value, str)
            else "numeric"
        )
        if self.data_type is None:
            self.data_type = inferred
        elif self.data_type == "categorical" and inferred != "categorical":
            self.value = str(self.value)
        elif self.data_type != "categorical" and inferred == "categorical":
            raise ValueError(f"A {self.data_type} score needs a number or boolean value")
        if isinstance(self.value, str) and len(self.value) > 255:
            raise ValueError("Categorical score labels are limited to 255 characters")
        return self


class ScoreIn(ScoreBase):
    """Score addressed by wire ids (what an SDK knows)."""

    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    span_id: str | None = Field(default=None, pattern="^[0-9a-f]{16}$")


class ScoreCreate(ScoreBase):
    """Score created from the dashboard on a known trace."""

    span_pk: uuid.UUID | None = None


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_pk: uuid.UUID
    span_pk: uuid.UUID | None
    name: str
    data_type: str
    value: float | None
    string_value: str | None
    comment: str | None
    source: str
    author_id: uuid.UUID | None
    meta: dict | None = None
    external_id: str | None = None
    created_at: datetime


class ScoreSeriesPoint(BaseModel):
    bucket_start: datetime
    count: int
    mean: float | None


class ScoreSummary(BaseModel):
    name: str
    data_type: str
    count: int
    mean: float | None
    min: float | None
    max: float | None
    # label → count, for categorical (and boolean, as "true"/"false") scores
    distribution: dict[str, int]
    series: list[ScoreSeriesPoint]


class ScoreConfigPut(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    data_type: ScoreDataType = "numeric"
    min_value: float | None = None
    max_value: float | None = None
    categories: list[str] | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=2000)


class ScoreConfigOut(ScoreConfigPut):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
