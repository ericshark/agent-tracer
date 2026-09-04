import uuid


def auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def otlp_payload(trace_id: str, span_id: str) -> dict:
    """A representative OTLP/HTTP JSON export with OpenInference attributes."""
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "my-agent"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "openinference.instrumentation"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": "ChatCompletion",
                                "kind": 3,
                                "startTimeUnixNano": "1754300000000000000",
                                "endTimeUnixNano": "1754300002500000000",
                                "status": {"code": 1},
                                "attributes": [
                                    {
                                        "key": "openinference.span.kind",
                                        "value": {"stringValue": "LLM"},
                                    },
                                    {
                                        "key": "llm.model_name",
                                        "value": {"stringValue": "claude-sonnet-5"},
                                    },
                                    {
                                        "key": "llm.token_count.prompt",
                                        "value": {"intValue": "230"},
                                    },
                                    {
                                        "key": "llm.token_count.completion",
                                        "value": {"intValue": "120"},
                                    },
                                    {
                                        "key": "input.value",
                                        "value": {
                                            "stringValue": (
                                                '{"messages": [{"role": "user",'
                                                ' "content": "summarize"}]}'
                                            )
                                        },
                                    },
                                    {
                                        "key": "input.mime_type",
                                        "value": {"stringValue": "application/json"},
                                    },
                                    {
                                        "key": "output.value",
                                        "value": {"stringValue": "A summary."},
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


async def test_otlp_ingest_maps_openinference(user_client, project, api_key):
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex
    response = await client.post(
        "/v1/traces", json=otlp_payload(trace_id, "ab" * 8), headers=auth(api_key)
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"partialSuccess": {}}

    listed = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    trace = listed.json()["items"][0]
    assert trace["llm_call_count"] == 1
    assert trace["input_tokens"] == 230

    detail = await client.get(f"/api/traces/{trace['id']}", headers=headers)
    span = detail.json()["spans"][0]
    assert span["kind"] == "LLM"
    assert span["model"] == "claude-sonnet-5"
    assert span["input"] == {"messages": [{"role": "user", "content": "summarize"}]}
    assert span["output"] == "A summary."
    assert span["duration_ms"] == 2500.0
    # cost derived from the pricing table
    assert span["cost_usd"] is not None


async def test_otlp_exception_event_maps_to_error(user_client, project, api_key):
    client, headers, _user = user_client
    trace_id = uuid.uuid4().hex
    payload = otlp_payload(trace_id, "cd" * 8)
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["status"] = {"code": 2, "message": "boom"}
    span["events"] = [
        {
            "name": "exception",
            "timeUnixNano": "1754300001000000000",
            "attributes": [
                {"key": "exception.type", "value": {"stringValue": "ValueError"}},
                {"key": "exception.message", "value": {"stringValue": "bad input"}},
            ],
        }
    ]
    await client.post("/v1/traces", json=payload, headers=auth(api_key))

    listed = await client.get(
        f"/api/projects/{project['id']}/traces?status=error", headers=headers
    )
    trace = listed.json()["items"][0]
    detail = await client.get(f"/api/traces/{trace['id']}", headers=headers)
    span_out = detail.json()["spans"][0]
    assert span_out["status"] == "error"
    assert span_out["error_type"] == "ValueError"
    assert span_out["error_message"] == "bad input"


async def test_otlp_rejects_malformed_body(client, api_key):
    response = await client.post(
        "/v1/traces",
        content=b"not json",
        headers={**auth(api_key), "Content-Type": "application/json"},
    )
    assert response.status_code == 400
