import json

import httpx
import pytest
from agent_tracer import ApiError
from agent_tracer.api import ApiClient
from agent_tracer.datasets import DatasetsClient


def make_client(handler):
    api = ApiClient("http://collector.invalid", "at_test", transport=httpx.MockTransport(handler))
    return DatasetsClient(api)


def test_get_pages_through_items():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer at_test"
        offset = int(request.url.params["offset"])
        calls.append(offset)
        page = [{"id": f"i{n}", "input": n, "expected_output": n * 2} for n in range(offset, 501)]
        return httpx.Response(
            200,
            json={"id": "d1", "name": "my set", "item_count": 501, "items": page[:500]},
        )

    dataset = make_client(handler).get("my set")
    assert calls == [0, 500]
    assert len(dataset) == 501 and dataset.items[-1].expected_output == 1000


def test_add_items_accepts_dicts_and_pairs():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.extend(body["items"])
        return httpx.Response(201, json=[{}] * len(body["items"]))

    added = make_client(handler).add_items(
        "s", [{"input": {"q": 1}, "metadata": {"k": "v"}}, ("in", "out")]
    )
    assert added == 2
    assert sent[0] == {"input": {"q": 1}, "expected_output": None, "metadata": {"k": "v"}}
    assert sent[1]["expected_output"] == "out"
    with pytest.raises(ValueError):
        make_client(handler).add_items("s", ["just a string"])


def test_errors_raise_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Dataset 'x' not found"})

    with pytest.raises(ApiError) as excinfo:
        make_client(handler).get("x")
    assert excinfo.value.status_code == 404 and "not found" in excinfo.value.message


def test_missing_api_key_is_a_clear_error():
    client = DatasetsClient(ApiClient("http://collector.invalid", None))
    with pytest.raises(ApiError, match="no API key"):
        client.list()
