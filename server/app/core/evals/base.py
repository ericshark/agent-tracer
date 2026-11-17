import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpanView:
    """The slice of a span that evaluators need (decoupled from the ORM)."""

    name: str
    kind: str
    status: str
    input: Any = None
    output: Any = None
    duration_ms: float | None = None


@dataclass
class EvalContext:
    input: Any = None
    output: Any = None
    expected: Any = None
    # The run's spans in start order — the agent's trajectory.
    spans: list[SpanView] = field(default_factory=list)
    latency_ms: float | None = None
    cost_usd: float | None = None
    total_tokens: int | None = None


@dataclass
class EvalResult:
    value: float | bool | str | None
    data_type: str = "numeric"
    comment: str | None = None
    # Set when the evaluator could not run (missing data, bad config). No score is stored.
    error: str | None = None
    metadata: dict[str, Any] | None = None


class EvalConfigError(Exception):
    """The evaluator is misconfigured or lacks the data it needs."""


def passed(ok: bool, comment: str | None = None) -> EvalResult:
    return EvalResult(value=ok, data_type="boolean", comment=comment)


def as_text(value: Any) -> str:
    """Best-effort plain text of an input/output value.

    Chat-shaped values collapse to their text so string checks work on
    `{"role": "assistant", "content": "…"}` as well as on bare strings.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "text", "answer", "output", "result"):
            if key in value and len(value) <= 4:
                return as_text(value[key])
        if "messages" in value and isinstance(value["messages"], list):
            return "\n".join(as_text(m) for m in value["messages"])
    if isinstance(value, list) and all(isinstance(b, dict) and "text" in b for b in value):
        return "".join(str(b["text"]) for b in value)
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def as_json(value: Any) -> Any:
    """Parse JSON carried as text (optionally inside a ``` fence); else return as-is."""
    if not isinstance(value, str):
        if isinstance(value, dict) and set(value) <= {"role", "content", "stop_reason"}:
            return as_json(value.get("content"))
        return value
    text = value.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    return json.loads(text)
