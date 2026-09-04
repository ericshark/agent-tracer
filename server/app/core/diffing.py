"""Trace comparison: align two span trees and compute per-node deltas.

Alignment strategy: recursively match children of aligned parents by
(name, kind), in order of occurrence. This handles the common debugging
question — "this run failed, that run worked, what changed?" — where both
traces come from the same pipeline and mostly share structure.
"""

import json
from typing import Any

from app.core.timeutil import as_utc
from app.models import Span


def _sorted_children(spans: list[Span], parent_id: str | None) -> list[Span]:
    return sorted(
        (s for s in spans if s.parent_span_id == parent_id),
        key=lambda s: (as_utc(s.started_at), s.span_id),
    )


def _span_brief(span: Span) -> dict[str, Any]:
    return {
        "id": str(span.id),
        "span_id": span.span_id,
        "name": span.name,
        "kind": span.kind,
        "status": span.status,
        "duration_ms": span.duration_ms,
        "model": span.model,
        "input_tokens": span.input_tokens,
        "output_tokens": span.output_tokens,
        "cost_usd": span.cost_usd,
        "error_message": span.error_message,
    }


def _json_eq(a: Any, b: Any) -> bool:
    try:
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(
            b, sort_keys=True, default=str
        )
    except (TypeError, ValueError):
        return a == b


def _pair_delta(base: Span, other: Span) -> dict[str, Any]:
    delta: dict[str, Any] = {
        "status_changed": base.status != other.status,
        "input_changed": not _json_eq(base.input, other.input),
        "output_changed": not _json_eq(base.output, other.output),
    }
    if base.duration_ms is not None and other.duration_ms is not None:
        delta["duration_ms"] = round(other.duration_ms - base.duration_ms, 3)
    if base.input_tokens is not None or other.input_tokens is not None:
        delta["input_tokens"] = (other.input_tokens or 0) - (base.input_tokens or 0)
    if base.output_tokens is not None or other.output_tokens is not None:
        delta["output_tokens"] = (other.output_tokens or 0) - (base.output_tokens or 0)
    if base.cost_usd is not None or other.cost_usd is not None:
        delta["cost_usd"] = round((other.cost_usd or 0) - (base.cost_usd or 0), 8)
    return delta


def _align_level(
    base_children: list[Span], other_children: list[Span]
) -> list[tuple[Span | None, Span | None]]:
    pairs: list[tuple[Span | None, Span | None]] = []
    used_other: set[int] = set()
    # Match by (name, kind) — nth occurrence pairs with nth occurrence.
    for base_span in base_children:
        match_idx = next(
            (
                i
                for i, o in enumerate(other_children)
                if i not in used_other and o.name == base_span.name and o.kind == base_span.kind
            ),
            None,
        )
        if match_idx is None:
            pairs.append((base_span, None))
        else:
            used_other.add(match_idx)
            pairs.append((base_span, other_children[match_idx]))
    for i, other_span in enumerate(other_children):
        if i not in used_other:
            pairs.append((None, other_span))
    return pairs


def _diff_subtree(
    base_spans: list[Span],
    other_spans: list[Span],
    base_parent: str | None,
    other_parent: str | None,
    depth: int,
) -> list[dict[str, Any]]:
    if depth > 50:
        return []
    nodes: list[dict[str, Any]] = []
    pairs = _align_level(
        _sorted_children(base_spans, base_parent),
        _sorted_children(other_spans, other_parent),
    )
    for base_span, other_span in pairs:
        if base_span is not None and other_span is not None:
            node = {
                "change": "matched",
                "base": _span_brief(base_span),
                "other": _span_brief(other_span),
                "delta": _pair_delta(base_span, other_span),
                "children": _diff_subtree(
                    base_spans, other_spans, base_span.span_id, other_span.span_id, depth + 1
                ),
            }
        elif base_span is not None:
            node = {
                "change": "removed",
                "base": _span_brief(base_span),
                "other": None,
                "delta": None,
                "children": _diff_subtree(
                    base_spans, other_spans, base_span.span_id, "__none__", depth + 1
                ),
            }
        else:
            assert other_span is not None
            node = {
                "change": "added",
                "base": None,
                "other": _span_brief(other_span),
                "delta": None,
                "children": _diff_subtree(
                    base_spans, other_spans, "__none__", other_span.span_id, depth + 1
                ),
            }
        nodes.append(node)
    return nodes


def diff_traces(base_spans: list[Span], other_spans: list[Span]) -> dict[str, Any]:
    nodes = _diff_subtree(base_spans, other_spans, None, None, 0)

    def count(nodes: list[dict[str, Any]], change: str) -> int:
        total = 0
        for n in nodes:
            if n["change"] == change:
                total += 1
            total += count(n["children"], change)
        return total

    changed = 0

    def count_changed(nodes: list[dict[str, Any]]) -> None:
        nonlocal changed
        for n in nodes:
            d = n.get("delta")
            if d and (d["status_changed"] or d["input_changed"] or d["output_changed"]):
                changed += 1
            count_changed(n["children"])

    count_changed(nodes)
    return {
        "nodes": nodes,
        "summary": {
            "matched": count(nodes, "matched"),
            "added": count(nodes, "added"),
            "removed": count(nodes, "removed"),
            "changed": changed,
        },
    }
