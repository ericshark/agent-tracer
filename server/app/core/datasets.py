"""Dataset helpers: capturing recorded runs and parsing uploads."""

import csv
import io
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import as_utc
from app.models import Dataset, DatasetItem, Span, Trace
from app.schemas.datasets import MAX_ITEMS_PER_REQUEST, DatasetItemIn


class DatasetError(Exception):
    """User-facing dataset validation error (mapped to HTTP 400)."""


async def item_counts(db: AsyncSession, dataset_ids: list) -> dict:
    if not dataset_ids:
        return {}
    result = await db.execute(
        select(DatasetItem.dataset_id, func.count())
        .where(DatasetItem.dataset_id.in_(dataset_ids), DatasetItem.archived_at.is_(None))
        .group_by(DatasetItem.dataset_id)
    )
    return dict(result.all())


def add_items(
    db: AsyncSession, dataset: Dataset, items: list[DatasetItemIn]
) -> list[DatasetItem]:
    rows = [
        DatasetItem(
            dataset_id=dataset.id,
            project_id=dataset.project_id,
            input=item.input,
            expected_output=item.expected_output,
            meta=item.metadata,
        )
        for item in items
    ]
    db.add_all(rows)
    return rows


def root_span(trace: Trace) -> Span | None:
    roots = [s for s in trace.spans if s.parent_span_id is None] or list(trace.spans)
    return min(roots, key=lambda s: as_utc(s.started_at), default=None)


def item_from_span(dataset: Dataset, trace: Trace, span: Span) -> DatasetItem:
    return DatasetItem(
        dataset_id=dataset.id,
        project_id=dataset.project_id,
        input=span.input,
        expected_output=span.output,
        meta={"source": "trace", "trace_id": trace.trace_id, "span_name": span.name},
        source_trace_pk=trace.id,
        source_span_pk=span.id,
    )


# ---------------------------------------------------------------------- import


def _maybe_json(text: str) -> Any:
    stripped = text.strip()
    if stripped == "":
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return text


def parse_import(fmt: str, content: str) -> list[DatasetItemIn]:
    try:
        items = _parse_jsonl(content) if fmt == "jsonl" else _parse_csv(content)
    except ValueError as exc:
        raise DatasetError(str(exc)) from exc
    if not items:
        raise DatasetError("The file contains no items")
    if len(items) > MAX_ITEMS_PER_REQUEST:
        raise DatasetError(f"At most {MAX_ITEMS_PER_REQUEST} items per import")
    return items


def _item(record: dict[str, Any], where: str) -> DatasetItemIn:
    """`input` / `expected_output` / `metadata` keys are used as-is; any other
    shape is treated as the input itself."""
    if "input" in record:
        metadata = record.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError(f"{where}: `metadata` must be an object")
        expected = record.get("expected_output", record.get("expected"))
        return DatasetItemIn(input=record["input"], expected_output=expected, metadata=metadata)
    return DatasetItemIn(input=record)


def _parse_jsonl(content: str) -> list[DatasetItemIn]:
    items = []
    for number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"Line {number}: invalid JSON ({exc})") from exc
        if not isinstance(record, dict):
            record = {"input": record}
        items.append(_item(record, f"Line {number}"))
    return items


def _parse_csv(content: str) -> list[DatasetItemIn]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("The CSV file has no header row")
    items = []
    for number, row in enumerate(reader, start=2):
        record = {k: _maybe_json(v or "") for k, v in row.items() if k}
        if "input" not in record:
            # No `input` column: every non-reserved column is part of the input.
            reserved = ("expected_output", "expected", "metadata")
            record = {
                "input": {k: v for k, v in record.items() if k not in reserved},
                **{k: v for k, v in record.items() if k in reserved},
            }
        items.append(_item(record, f"Row {number}"))
    return items


def export_jsonl(items: list[DatasetItem]) -> str:
    lines = []
    for item in items:
        record: dict[str, Any] = {"input": item.input, "expected_output": item.expected_output}
        if item.meta:
            record["metadata"] = item.meta
        lines.append(json.dumps(record, default=str, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")
