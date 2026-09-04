"""OTLP/HTTP JSON → native span translation.

Lets existing OpenTelemetry-instrumented apps (e.g. via OpenInference
instrumentors) point their OTLP HTTP exporter at Agent Tracer:

    OTEL_EXPORTER_OTLP_ENDPOINT=https://tracer.example.com
    (the exporter appends /v1/traces)

We map the OTLP proto-JSON shape (resourceSpans → scopeSpans → spans, with
attributes as {key, value:{stringValue|intValue|…}} pairs) and translate
OpenInference semantic conventions into native fields.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.schemas.ingest import SpanErrorIn, SpanIn

logger = logging.getLogger(__name__)

# OpenInference span kinds → native kinds
_OI_KIND_MAP = {
    "AGENT": "AGENT",
    "LLM": "LLM",
    "TOOL": "TOOL",
    "CHAIN": "CHAIN",
    "RETRIEVER": "RETRIEVER",
    "EMBEDDING": "EMBEDDING",
    "GUARDRAIL": "GUARDRAIL",
    "RERANKER": "RETRIEVER",
    "EVALUATOR": "GUARDRAIL",
}


def _anyvalue(value: dict[str, Any]) -> Any:
    """Decode an OTLP AnyValue."""
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "arrayValue" in value:
        return [_anyvalue(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return {
            kv["key"]: _anyvalue(kv.get("value", {}))
            for kv in value["kvlistValue"].get("values", [])
        }
    if "bytesValue" in value:
        return value["bytesValue"]
    return None


def _attributes(raw: list[dict[str, Any]] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in raw or []:
        key = kv.get("key")
        if key:
            out[key] = _anyvalue(kv.get("value", {}))
    return out


def _nanos_to_dt(nanos: Any) -> datetime | None:
    try:
        n = int(nanos)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return datetime.fromtimestamp(n / 1e9, tz=UTC)


def _maybe_json(value: Any, mime: str | None) -> Any:
    if isinstance(value, str) and (mime == "application/json" or value[:1] in "[{"):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _int_attr(attrs: dict[str, Any], key: str) -> int | None:
    v = attrs.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def otlp_to_spans(payload: dict[str, Any]) -> list[SpanIn]:
    """Translate an OTLP ExportTraceServiceRequest (JSON) into native spans."""
    spans: list[SpanIn] = []
    for resource_spans in payload.get("resourceSpans", []):
        for scope_spans in resource_spans.get("scopeSpans", []):
            for raw in scope_spans.get("spans", []):
                span = _translate_span(raw)
                if span is not None:
                    spans.append(span)
    return spans


def _translate_span(raw: dict[str, Any]) -> SpanIn | None:
    trace_id = str(raw.get("traceId", "")).lower()
    span_id = str(raw.get("spanId", "")).lower()
    if len(trace_id) != 32 or len(span_id) != 16:
        logger.warning("Skipping OTLP span with malformed ids: %s/%s", trace_id, span_id)
        return None

    attrs = _attributes(raw.get("attributes"))
    started_at = _nanos_to_dt(raw.get("startTimeUnixNano"))
    ended_at = _nanos_to_dt(raw.get("endTimeUnixNano"))
    if started_at is None:
        return None

    oi_kind = str(attrs.pop("openinference.span.kind", "") or "").upper()
    kind = _OI_KIND_MAP.get(oi_kind, "UNKNOWN")

    status_obj = raw.get("status") or {}
    status_code = status_obj.get("code")
    is_error = status_code in (2, "STATUS_CODE_ERROR")
    status = "error" if is_error else ("ok" if ended_at else "running")

    input_value = _maybe_json(attrs.pop("input.value", None), attrs.pop("input.mime_type", None))
    output_value = _maybe_json(
        attrs.pop("output.value", None), attrs.pop("output.mime_type", None)
    )

    model = attrs.pop("llm.model_name", None) or attrs.pop("gen_ai.request.model", None)
    input_tokens = _int_attr(attrs, "llm.token_count.prompt") or _int_attr(
        attrs, "gen_ai.usage.input_tokens"
    )
    output_tokens = _int_attr(attrs, "llm.token_count.completion") or _int_attr(
        attrs, "gen_ai.usage.output_tokens"
    )

    error: SpanErrorIn | None = None
    events_out: list[dict[str, Any]] = []
    for event in raw.get("events", []) or []:
        event_attrs = _attributes(event.get("attributes"))
        event_entry = {
            "name": event.get("name", "event"),
            "timestamp": (_nanos_to_dt(event.get("timeUnixNano")) or started_at).isoformat(),
            "attributes": event_attrs,
        }
        events_out.append(event_entry)
        if event.get("name") == "exception" and error is None:
            error = SpanErrorIn(
                type=event_attrs.get("exception.type"),
                message=event_attrs.get("exception.message"),
                stacktrace=event_attrs.get("exception.stacktrace"),
            )
    if is_error and error is None:
        error = SpanErrorIn(type="Error", message=status_obj.get("message"))

    parent = str(raw.get("parentSpanId", "") or "").lower() or None

    return SpanIn(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        name=str(raw.get("name") or "span")[:255],
        kind=kind,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        input=input_value,
        output=output_value,
        attributes=attrs or None,
        events=events_out or None,
        model=str(model)[:128] if model else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )
