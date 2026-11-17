import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scores import ScoreBase

# ------------------------------------------------------------------ evaluators


class TemplateParamOut(BaseModel):
    name: str
    type: str
    description: str
    default: Any = None
    required: bool = False
    options: list[str] = Field(default_factory=list)


class TemplateOut(BaseModel):
    key: str
    kind: str
    title: str
    description: str
    data_type: str
    needs_expected: bool
    needs_trace: bool
    params: list[TemplateParamOut]


class EvaluatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template: str = Field(min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)


class EvaluatorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: dict[str, Any] | None = None


class EvaluatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    template: str
    config: dict
    created_at: datetime


class DryRun(BaseModel):
    """Try an evaluator on a recorded trace without saving anything."""

    template: str
    config: dict[str, Any] = Field(default_factory=dict)
    trace_pk: uuid.UUID
    span_pk: uuid.UUID | None = None
    expected: Any = None


class EvalResultOut(BaseModel):
    name: str | None = None
    value: float | bool | str | None
    data_type: str
    comment: str | None = None
    error: str | None = None


class EvaluateTrace(BaseModel):
    evaluator_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    span_pk: uuid.UUID | None = None


# ----------------------------------------------------------------- experiments


class PromptTarget(BaseModel):
    """Run a model over each test case.

    `messages` is a template: `{{input}}` inserts the whole input and
    `{{input.field}}` a field of it. Without a template, an input that is
    already a recorded model call (messages / prompt / string) is replayed
    as-is — which makes "the same traffic on a different model" one click.
    """

    type: Literal["prompt"] = "prompt"
    model: str = Field(min_length=1, max_length=128)
    provider: Literal["simulation", "anthropic", "openai"] | None = None
    system: str | None = Field(default=None, max_length=32768)
    messages: list[dict[str, Any]] | None = Field(default=None, max_length=64)
    max_tokens: int = Field(default=4096, ge=1, le=64000)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    dataset_id: uuid.UUID
    target: PromptTarget
    evaluator_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] | None = None


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: str
    dataset_id: uuid.UUID | None
    target: dict
    evaluator_ids: list
    summary: dict | None
    meta: dict | None = None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    item_count: int = 0
    completed_count: int = 0


class ExperimentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_item_id: uuid.UUID | None
    input: Any
    expected_output: Any
    output: Any
    status: str
    error: str | None
    trace_pk: uuid.UUID | None
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    scores: dict | None


class ExperimentItemList(BaseModel):
    items: list[ExperimentItemOut]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------- SDK-facing (/v1)


class SdkExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    dataset: str | None = Field(default=None, max_length=120)
    # Names of server-side evaluators to run once results are in.
    evaluators: list[str] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] | None = None


class SdkItemScore(ScoreBase):
    pass


class SdkExperimentItem(BaseModel):
    dataset_item_id: uuid.UUID | None = None
    input: Any = None
    expected_output: Any = None
    output: Any = None
    error: str | None = Field(default=None, max_length=8192)
    trace_id: str | None = Field(default=None, pattern="^[0-9a-f]{32}$")
    latency_ms: float | None = Field(default=None, ge=0)
    # Scores computed by evaluators that ran in your process.
    scores: list[SdkItemScore] = Field(default_factory=list, max_length=100)


class SdkExperimentItems(BaseModel):
    items: list[SdkExperimentItem] = Field(min_length=1, max_length=500)
