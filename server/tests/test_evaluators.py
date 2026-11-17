import pytest
from app.core.evals.base import EvalConfigError, EvalContext, SpanView
from app.core.evals.registry import TEMPLATES, run_evaluator, validate_config


async def run(key, ctx, **config):
    return await run_evaluator(key, config, ctx, creds={})


def tool(name, status="ok", input=None):
    return SpanView(name=name, kind="TOOL", status=status, input=input)


TRAJECTORY = [
    SpanView(name="plan", kind="LLM", status="ok"),
    tool("search_flights", input={"to": "Tokyo"}),
    tool("search_hotels", input={"city": "Tokyo"}),
    SpanView(name="compose", kind="LLM", status="ok"),
]


async def test_text_evaluators():
    ctx = EvalContext(output={"role": "assistant", "content": " Paris "}, expected="paris")
    assert (await run("exact_match", ctx)).value is False
    assert (await run("exact_match", ctx, ignore_case=True)).value is True
    assert (await run("contains", ctx, substring="ari")).value is True
    assert (await run("regex_match", ctx, pattern=r"^\s*P\w+")).value is True
    assert (await run("similarity", EvalContext(output="abcd", expected="abcf"))).value == 0.75
    assert (
        await run("numeric_close", EvalContext(output="3.14", expected="3.1"), tolerance=0.1)
    ).value


async def test_json_evaluators():
    good = EvalContext(output='```json\n{"city": "Paris", "nights": 3}\n```')
    assert (await run("json_valid", good)).value is True
    assert (await run("json_valid", EvalContext(output="{nope"))).value is False
    schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}, "nights": {"type": "integer"}},
        "required": ["city", "nights"],
    }
    assert (await run("json_schema", good, schema=schema)).value is True
    bad = await run("json_schema", EvalContext(output='{"city": 3}'), schema=schema)
    assert bad.value is False and bad.comment


async def test_budget_evaluators():
    ctx = EvalContext(latency_ms=1200, cost_usd=0.02, total_tokens=900)
    assert (await run("latency_under", ctx, max_ms=2000)).value is True
    assert (await run("cost_under", ctx, max_usd=0.01)).value is False
    assert (await run("tokens_under", ctx, max_tokens=1000)).value is True
    missing = await run("latency_under", EvalContext(), max_ms=10)
    assert missing.value is None and "measurement" in missing.error


async def test_tool_sequence_modes():
    ctx = EvalContext(spans=TRAJECTORY)
    both = ["search_flights", "search_hotels"]
    assert (await run("tool_sequence", ctx, tools=both, mode="exact")).value is True
    assert (await run("tool_sequence", ctx, tools=["search_hotels"], mode="exact")).value is False
    assert (await run("tool_sequence", ctx, tools=["search_hotels"], mode="in_order")).value is True
    assert (await run("tool_sequence", ctx, tools=both[::-1], mode="in_order")).value is False
    assert (await run("tool_sequence", ctx, tools=both[::-1], mode="any_order")).value is True
    # Expected tools can come from the test case instead of the config.
    from_case = EvalContext(spans=TRAJECTORY, expected={"tools": both})
    assert (await run("tool_sequence", from_case, mode="exact")).value is True


async def test_tool_usage_evaluators():
    ctx = EvalContext(spans=TRAJECTORY)
    assert (await run("required_tools", ctx, tools=["search_flights"])).value is True
    assert (await run("required_tools", ctx, tools=["book"])).value is False
    assert (await run("forbidden_tools", ctx, tools=["delete_booking"])).value is True
    assert (await run("forbidden_tools", ctx, tools=["search_hotels"])).value is False
    assert (await run("tool_args_match", ctx, tool="search_flights", args={"to": "Tokyo"})).value
    assert not (await run("tool_args_match", ctx, tool="search_flights", args={"to": "Oslo"})).value
    assert (await run("max_steps", ctx, max=4)).value is True
    assert (await run("max_steps", ctx, max=3)).value is False


async def test_tool_health_evaluators():
    flaky = [tool("a"), tool("a", status="error"), tool("b"), tool("b")]
    assert (await run("tool_success_rate", EvalContext(spans=flaky))).value == 0.75
    repeated = [tool("a", input={"q": 1}), tool("b"), tool("a", input={"q": 1})]
    assert (await run("no_redundant_calls", EvalContext(spans=repeated))).value is False
    assert (await run("no_redundant_calls", EvalContext(spans=TRAJECTORY))).value is True
    looping = [tool("poll")] * 5
    assert (await run("no_loops", EvalContext(spans=looping), max_repeats=3)).value is False
    assert (await run("no_loops", EvalContext(spans=TRAJECTORY))).value is True


async def test_trajectory_evaluators_need_a_trace():
    result = await run("required_tools", EvalContext(output="x"), tools=["a"])
    assert result.value is None and "trace" in result.error


async def test_simulated_judges_are_deterministic_and_marked():
    close = EvalContext(input="Capital of France?", output="Paris", expected="Paris")
    far = EvalContext(input="Capital of France?", output="I like trains", expected="Paris")
    good, bad = await run("correctness", close), await run("correctness", far)
    assert good.value == 1.0 and bad.value < 0.5
    assert good.comment.startswith("[simulated judge]")
    assert (await run("correctness", close)).value == good.value

    needs_reference = await run("correctness", EvalContext(output="Paris"))
    assert needs_reference.value is None and "expected" in needs_reference.error

    failed_run = EvalContext(input="book it", output="done", spans=[tool("book", status="error")])
    assert (await run("task_completion", failed_run)).value == 0.25
    assert (await run("custom", close, rubric="Be brief")).value is not None
    assert (await run("custom", close)).error


async def test_judge_parses_structured_verdict(monkeypatch):
    from app.core import llm
    from app.core.evals import judge

    seen = {}

    async def fake_complete(request, creds):
        seen["request"] = request
        return llm.LLMResult(
            output={"role": "assistant", "content": '{"reasoning": "Matches.", "rating": 4}'},
            input_tokens=100,
            output_tokens=20,
        )

    monkeypatch.setattr(judge, "complete", fake_complete)
    ctx = EvalContext(input="q", output="a", expected="a")
    result = await run_evaluator("correctness", {}, ctx, {"anthropic": ("key", None)})
    assert result.value == 0.75 and result.comment == "Matches."
    assert result.metadata["judge_model"] == "claude-opus-5-5"
    request = seen["request"]
    assert request.provider == "anthropic" and request.json_schema["required"] == [
        "reasoning",
        "rating",
    ]
    assert "<reference>" in request.messages[0]["content"]


def test_validate_config():
    validate_config("regex_match", {"pattern": "x"})
    with pytest.raises(EvalConfigError, match="required"):
        validate_config("regex_match", {})
    with pytest.raises(EvalConfigError, match="Unknown settings"):
        validate_config("exact_match", {"nope": 1})
    with pytest.raises(EvalConfigError, match="one of"):
        validate_config("tool_sequence", {"mode": "fuzzy"})
    with pytest.raises(EvalConfigError, match="Unknown evaluator"):
        validate_config("nope", {})
    assert {t.kind for t in TEMPLATES.values()} == {"code", "trajectory", "llm_judge"}
