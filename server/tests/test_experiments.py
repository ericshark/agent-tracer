import uuid

from app.core.experiments import build_messages, render
from app.core.jobs import drain_jobs

from tests.conftest import make_span


def key_auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _dataset(client, headers, project, items, name="capitals"):
    dataset = (
        await client.post(
            f"/api/projects/{project['id']}/datasets", json={"name": name}, headers=headers
        )
    ).json()
    created = await client.post(
        f"/api/datasets/{dataset['id']}/items", json={"items": items}, headers=headers
    )
    assert created.status_code == 201, created.text
    return dataset, created.json()


async def _evaluator(client, headers, project, name, template, **config):
    response = await client.post(
        f"/api/projects/{project['id']}/evaluators",
        json={"name": name, "template": template, "config": config},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


CASES = [
    {"input": {"question": "Capital of France?"}, "expected_output": "Paris"},
    {"input": {"question": "Capital of Japan?"}, "expected_output": "Tokyo"},
]


def test_prompt_templates():
    assert (
        render(
            "Q: {{input.question}} ({{ input.meta.lang }})",
            {"question": "hi", "meta": {"lang": "en"}},
        )
        == "Q: hi (en)"
    )
    assert render("{{input}}", "plain") == "plain"
    assert render("{{input.missing}}!", {"a": 1}) == "!"

    messages, system = build_messages(
        {
            "system": "Answer in {{input.lang}}",
            "messages": [{"role": "user", "content": "{{input.q}}"}],
        },
        {"q": "hello", "lang": "French"},
    )
    assert messages == [{"role": "user", "content": "hello"}] and system == "Answer in French"

    # No template: a recorded model call is replayed as-is.
    recorded = {"system": "be brief", "messages": [{"role": "user", "content": "hi"}]}
    assert build_messages({}, recorded) == ([{"role": "user", "content": "hi"}], "be brief")
    assert build_messages({}, {"question": "x"})[0][0]["role"] == "user"


async def test_evaluator_catalog_and_crud(user_client, project):
    client, headers, _ = user_client
    templates = (await client.get("/api/evaluator-templates", headers=headers)).json()
    kinds = {t["kind"] for t in templates}
    assert kinds == {"code", "trajectory", "llm_judge"}
    assert next(t for t in templates if t["key"] == "tool_sequence")["needs_trace"] is True

    url = f"/api/projects/{project['id']}/evaluators"
    bad = await client.post(
        url, json={"name": "x", "template": "regex_match", "config": {}}, headers=headers
    )
    assert bad.status_code == 400 and "pattern" in bad.json()["detail"]

    created = await _evaluator(client, headers, project, "has-digits", "regex_match", pattern="\\d")
    dup = await client.post(
        url,
        json={"name": "has-digits", "template": "json_valid", "config": {}},
        headers=headers,
    )
    assert dup.status_code == 409
    patched = await client.patch(
        f"/api/evaluators/{created['id']}", json={"config": {"pattern": "[a-z]"}}, headers=headers
    )
    assert patched.json()["config"] == {"pattern": "[a-z]"}
    assert (await client.get(url, headers=headers)).json()[0]["name"] == "has-digits"
    deleted = await client.delete(f"/api/evaluators/{created['id']}", headers=headers)
    assert deleted.status_code == 204


async def test_prompt_experiment_runs_scores_and_summarises(user_client, project):
    client, headers, _ = user_client
    dataset, _ = await _dataset(client, headers, project, CASES)
    judge = await _evaluator(client, headers, project, "correctness", "correctness")
    budget = await _evaluator(client, headers, project, "fast", "latency_under", max_ms=60_000)

    created = await client.post(
        f"/api/projects/{project['id']}/experiments",
        json={
            "name": "baseline",
            "dataset_id": dataset["id"],
            "target": {
                "model": "claude-opus-5-5",
                "system": "Answer with the city only.",
                "messages": [{"role": "user", "content": "{{input.question}}"}],
            },
            "evaluator_ids": [judge["id"], budget["id"]],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    experiment = created.json()
    assert experiment["status"] == "pending" and experiment["item_count"] == 2

    assert await drain_jobs() == 1
    experiment = (await client.get(f"/api/experiments/{experiment['id']}", headers=headers)).json()
    assert experiment["status"] == "completed" and experiment["completed_count"] == 2
    summary = experiment["summary"]
    assert summary["item_count"] == 2 and summary["error_count"] == 0
    assert summary["scores"]["fast"]["mean"] == 1.0
    assert summary["scores"]["correctness"]["count"] == 2

    items = (
        await client.get(f"/api/experiments/{experiment['id']}/items", headers=headers)
    ).json()["items"]
    first = items[0]
    assert first["status"] == "ok" and first["output"]["simulated"] is True
    assert first["scores"]["correctness"]["comment"].startswith("[simulated judge]")

    # Every run is also an ordinary trace: rendered prompt in, scores attached.
    detail = (await client.get(f"/api/traces/{first['trace_pk']}", headers=headers)).json()
    assert detail["environment"] == "experiment" and detail["scores"]["fast"] == 1.0
    llm_input = detail["spans"][0]["input"]
    assert llm_input["messages"][0]["content"] == "Capital of France?"
    assert llm_input["system"] == "Answer with the city only."

    # …but experiment traffic stays out of the production list and stats.
    listing = await client.get(f"/api/projects/{project['id']}/traces", headers=headers)
    assert listing.json()["total"] == 0
    stats = await client.get(f"/api/projects/{project['id']}/stats", headers=headers)
    assert stats.json()["trace_count"] == 0
    only_experiments = await client.get(
        f"/api/projects/{project['id']}/traces?environment=experiment", headers=headers
    )
    assert only_experiments.json()["total"] == 2


async def test_experiment_requires_cases_and_known_evaluators(user_client, project):
    client, headers, _ = user_client
    empty = (
        await client.post(
            f"/api/projects/{project['id']}/datasets", json={"name": "empty"}, headers=headers
        )
    ).json()
    body = {"name": "x", "dataset_id": empty["id"], "target": {"model": "m"}}
    response = await client.post(
        f"/api/projects/{project['id']}/experiments", json=body, headers=headers
    )
    assert response.status_code == 400

    dataset, _ = await _dataset(client, headers, project, CASES)
    response = await client.post(
        f"/api/projects/{project['id']}/experiments",
        json={**body, "dataset_id": dataset["id"], "evaluator_ids": [str(uuid.uuid4())]},
        headers=headers,
    )
    assert response.status_code == 404


async def test_sdk_experiment_with_trajectory_evaluator(user_client, project, api_key):
    client, headers, _ = user_client
    dataset, cases = await _dataset(client, headers, project, CASES)
    await _evaluator(client, headers, project, "used-search", "required_tools", tools=["search"])
    await _evaluator(client, headers, project, "exact", "exact_match", ignore_case=True)

    opened = await client.post(
        "/v1/experiments",
        json={
            "name": "agent-v2",
            "dataset": "capitals",
            "evaluators": ["used-search", "exact"],
            "metadata": {"git_sha": "abc123"},
        },
        headers=key_auth(api_key),
    )
    assert opened.status_code == 201, opened.text
    experiment_id = opened.json()["id"]

    # The task ran in the client's process and was traced like production code.
    trace_ids = [uuid.uuid4().hex, uuid.uuid4().hex]
    spans = []
    for index, trace_id in enumerate(trace_ids):
        root = uuid.uuid4().hex[:16]
        spans.append(make_span(trace_id=trace_id, span_id=root, name="agent"))
        if index == 0:  # only the first run actually used the tool
            spans.append(make_span(trace_id=trace_id, parent=root, kind="TOOL", name="search"))
    await client.post(
        "/v1/ingest",
        json={
            "traces": [{"trace_id": t, "environment": "experiment"} for t in trace_ids],
            "spans": spans,
        },
        headers=key_auth(api_key),
    )

    uploaded = await client.post(
        f"/v1/experiments/{experiment_id}/items",
        json={
            "items": [
                {
                    "dataset_item_id": cases[0]["id"],
                    "input": cases[0]["input"],
                    "expected_output": "Paris",
                    "output": "paris",
                    "trace_id": trace_ids[0],
                    "latency_ms": 420,
                    "scores": [{"name": "local-check", "value": True}],
                },
                {
                    "dataset_item_id": cases[1]["id"],
                    "input": cases[1]["input"],
                    "expected_output": "Tokyo",
                    "output": "Kyoto",
                    "trace_id": trace_ids[1],
                    "latency_ms": 380,
                },
            ]
        },
        headers=key_auth(api_key),
    )
    assert uploaded.status_code == 201 and uploaded.json() == {"accepted": 2}

    done = await client.post(f"/v1/experiments/{experiment_id}/complete", headers=key_auth(api_key))
    assert done.status_code == 200
    await drain_jobs()
    experiment = (
        await client.get(f"/v1/experiments/{experiment_id}", headers=key_auth(api_key))
    ).json()
    assert experiment["status"] == "completed", experiment
    scores = experiment["summary"]["scores"]
    assert scores["exact"]["mean"] == 0.5
    assert scores["used-search"]["mean"] == 0.5  # judged from the uploaded trajectory
    assert scores["local-check"]["count"] == 1
    assert experiment["meta"] == {"git_sha": "abc123"}

    late = await client.post(
        f"/v1/experiments/{experiment_id}/items",
        json={"items": [{"input": 1, "output": 2}]},
        headers=key_auth(api_key),
    )
    assert late.status_code == 409


async def test_compare_reports_regressions_against_baseline(user_client, project, api_key):
    client, headers, _ = user_client
    _, cases = await _dataset(client, headers, project, CASES)
    await _evaluator(client, headers, project, "exact", "exact_match")

    async def run(name, outputs):
        opened = await client.post(
            "/v1/experiments",
            json={"name": name, "dataset": "capitals", "evaluators": ["exact"]},
            headers=key_auth(api_key),
        )
        experiment_id = opened.json()["id"]
        await client.post(
            f"/v1/experiments/{experiment_id}/items",
            json={
                "items": [
                    {
                        "dataset_item_id": case["id"],
                        "input": case["input"],
                        "expected_output": case["expected_output"],
                        "output": output,
                    }
                    for case, output in zip(cases, outputs, strict=True)
                ]
            },
            headers=key_auth(api_key),
        )
        await client.post(f"/v1/experiments/{experiment_id}/complete", headers=key_auth(api_key))
        await drain_jobs()
        return experiment_id

    base = await run("base", ["Paris", "Tokyo"])
    worse = await run("candidate", ["Paris", "Osaka"])

    result = await client.get(f"/api/experiments/compare?ids={base},{worse}", headers=headers)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["baseline_id"] == base and len(data["rows"]) == 2
    base_stats, candidate = data["scores"]["exact"]
    assert base_stats["mean"] == 1.0 and "delta" not in base_stats
    assert candidate["mean"] == 0.5 and candidate["delta"] == -0.5
    assert (candidate["improved"], candidate["regressed"], candidate["unchanged"]) == (0, 1, 1)
    assert candidate["ci_low"] <= candidate["delta"] <= candidate["ci_high"]
    tokyo_row = next(r for r in data["rows"] if r["expected_output"] == "Tokyo")
    assert tokyo_row["cells"][worse]["output"] == "Osaka"

    one = await client.get(f"/api/experiments/compare?ids={base}", headers=headers)
    assert one.status_code == 400


async def test_evaluate_and_dry_run_on_recorded_trace(user_client, project, api_key):
    client, headers, _ = user_client
    trace_id, root = uuid.uuid4().hex, uuid.uuid4().hex[:16]
    await client.post(
        "/v1/ingest",
        json={
            "spans": [
                make_span(
                    trace_id=trace_id, span_id=root, name="agent", output="order 4521 shipped"
                ),
                make_span(trace_id=trace_id, parent=root, kind="TOOL", name="lookup_order"),
            ]
        },
        headers=key_auth(api_key),
    )
    trace = (await client.get(f"/api/projects/{project['id']}/traces", headers=headers)).json()[
        "items"
    ][0]

    dry = await client.post(
        f"/api/projects/{project['id']}/evaluators/dry-run",
        json={"template": "regex_match", "config": {"pattern": "\\d{4}"}, "trace_pk": trace["id"]},
        headers=headers,
    )
    assert dry.status_code == 200 and dry.json()["value"] is True
    assert (await client.get(f"/api/traces/{trace['id']}/scores", headers=headers)).json() == []

    lookup = await _evaluator(
        client, headers, project, "looked-up", "required_tools", tools=["lookup_order"]
    )
    exact = await _evaluator(client, headers, project, "exact", "exact_match")
    ran = await client.post(
        f"/api/traces/{trace['id']}/evaluate",
        json={"evaluator_ids": [lookup["id"], exact["id"]]},
        headers=headers,
    )
    assert ran.status_code == 200, ran.text
    by_name = {r["name"]: r for r in ran.json()}
    assert by_name["looked-up"]["value"] is True
    assert by_name["exact"]["error"]  # no expected output on a production trace
    saved = (await client.get(f"/api/traces/{trace['id']}/scores", headers=headers)).json()
    assert [(s["name"], s["source"], s["value"]) for s in saved] == [
        ("looked-up", "evaluator", 1.0)
    ]


async def test_experiments_are_isolated_between_users(user_client, project, api_key, client):
    owner_client, headers, _ = user_client
    opened = await owner_client.post(
        "/v1/experiments", json={"name": "private"}, headers=key_auth(api_key)
    )
    other = await client.post(
        "/api/auth/register",
        json={"email": "other-exp@example.com", "name": "Other", "password": "sup3r-secret-pw"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    experiment_id = opened.json()["id"]
    for path in (f"/api/experiments/{experiment_id}", f"/api/experiments/{experiment_id}/items"):
        assert (await client.get(path, headers=other_headers)).status_code == 404
