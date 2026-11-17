"""Datasets: named collections of test cases used by experiments."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from .api import ApiClient
from .serialize import safe_json

_PAGE = 500


@dataclass
class DatasetItem:
    id: str
    input: Any
    expected_output: Any = None
    metadata: dict[str, Any] | None = None


@dataclass
class Dataset:
    id: str
    name: str
    description: str | None = None
    items: list[DatasetItem] = field(default_factory=list)

    def __iter__(self) -> Iterator[DatasetItem]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


def _item_payload(item: Any) -> dict[str, Any]:
    """Accept {"input", "expected_output", "metadata"} dicts or (input, expected) pairs."""
    if isinstance(item, tuple) and len(item) == 2:
        item = {"input": item[0], "expected_output": item[1]}
    if not isinstance(item, dict) or "input" not in item:
        raise ValueError(
            "Each item must be a dict with an 'input' key or an (input, expected_output) pair"
        )
    return {
        "input": safe_json(item["input"]),
        "expected_output": safe_json(item.get("expected_output")),
        "metadata": safe_json(item.get("metadata")),
    }


class DatasetsClient:
    """Reached as `tracer.datasets`."""

    def __init__(self, api: ApiClient) -> None:
        self._api = api

    def list(self) -> list[Dataset]:
        return [
            Dataset(id=d["id"], name=d["name"], description=d.get("description"))
            for d in self._api.get("/v1/datasets")
        ]

    def create(self, name: str, description: str | None = None) -> Dataset:
        """Create the dataset, or return the existing one with this name."""
        data = self._api.post("/v1/datasets", {"name": name, "description": description})
        return Dataset(id=data["id"], name=data["name"], description=data.get("description"))

    def get(self, name: str) -> Dataset:
        """Fetch a dataset with all of its (non-archived) items."""
        path = f"/v1/datasets/{quote(name, safe='')}"
        offset = 0
        dataset: Dataset | None = None
        while True:
            data = self._api.get(path, limit=_PAGE, offset=offset)
            if dataset is None:
                dataset = Dataset(
                    id=data["id"], name=data["name"], description=data.get("description")
                )
            page = data["items"]
            dataset.items.extend(
                DatasetItem(
                    id=i["id"],
                    input=i["input"],
                    expected_output=i.get("expected_output"),
                    metadata=i.get("meta"),
                )
                for i in page
            )
            offset += len(page)
            if not page or offset >= data["item_count"]:
                return dataset

    def add_items(self, name: str, items: Iterable[Any]) -> int:
        """Append test cases. Returns how many were added."""
        payload = [_item_payload(i) for i in items]
        added = 0
        for start in range(0, len(payload), _PAGE):
            added += len(
                self._api.post(
                    f"/v1/datasets/{quote(name, safe='')}/items",
                    {"items": payload[start : start + _PAGE]},
                )
            )
        return added
