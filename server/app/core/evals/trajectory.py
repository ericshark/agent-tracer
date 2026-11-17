"""Trajectory evaluators: judge *how* an agent got there, not just the answer.

They read the run's spans (tool calls in start order), so they apply to
recorded production traces and to experiment runs that produced a trace.
"""

import json
from typing import Any

from app.core.evals.base import EvalConfigError, EvalContext, EvalResult, SpanView, passed


def _tools(ctx: EvalContext) -> list[SpanView]:
    if not ctx.spans:
        raise EvalConfigError("This evaluator needs a trace (no spans were recorded)")
    return [s for s in ctx.spans if s.kind == "TOOL"]


def _names(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise EvalConfigError(f"`{key}` must be a list of tool names")
    return value


def _expected_tools(ctx: EvalContext, config: dict[str, Any]) -> list[str]:
    """From config, else from the test case's expected output (`{"tools": [...]}`)."""
    if config.get("tools"):
        return _names(config["tools"], "tools")
    if isinstance(ctx.expected, dict) and "tools" in ctx.expected:
        return _names(ctx.expected["tools"], "expected.tools")
    raise EvalConfigError(
        'Set `tools`, or give the test case an expected output like {"tools": [...]}'
    )


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(name in it for name in needle)


def tool_sequence(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    """Did the agent call the expected tools?

    mode: "exact" (same calls, same order), "in_order" (expected calls appear
    in order, extras allowed) or "any_order" (same set of tools).
    """
    actual = [s.name for s in _tools(ctx)]
    expected = _expected_tools(ctx, config)
    mode = config.get("mode", "in_order")
    if mode == "exact":
        ok = actual == expected
    elif mode == "in_order":
        ok = _is_subsequence(expected, actual)
    elif mode == "any_order":
        ok = set(expected) <= set(actual)
    else:
        raise EvalConfigError("`mode` must be exact, in_order or any_order")
    return passed(ok, f"expected {expected} ({mode}), got {actual}")


def required_tools(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    called = {s.name for s in _tools(ctx)}
    missing = [t for t in _names(config.get("tools"), "tools") if t not in called]
    return passed(not missing, f"Missing: {missing}" if missing else None)


def forbidden_tools(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    banned = set(_names(config.get("tools"), "tools"))
    used = sorted({s.name for s in _tools(ctx)} & banned)
    return passed(not used, f"Called forbidden tools: {used}" if used else None)


def tool_args_match(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    """Some call to `tool` received every key/value in `args`."""
    tool, args = config.get("tool"), config.get("args")
    if not tool or not isinstance(args, dict):
        raise EvalConfigError("`tool` and an `args` object are required")
    calls = [s for s in _tools(ctx) if s.name == tool]
    if not calls:
        return passed(False, f"{tool} was never called")
    for call in calls:
        given = call.input if isinstance(call.input, dict) else {}
        if all(given.get(k) == v for k, v in args.items()):
            return passed(True)
    return passed(False, f"No call to {tool} had arguments {args}")


def max_steps(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    limit = config.get("max")
    if limit is None:
        raise EvalConfigError("`max` is required")
    if not ctx.spans:
        raise EvalConfigError("This evaluator needs a trace (no spans were recorded)")
    steps = sum(1 for s in ctx.spans if s.kind in ("LLM", "TOOL"))
    return passed(steps <= int(limit), f"{steps} model/tool steps (limit {int(limit)})")


def tool_success_rate(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    tools = _tools(ctx)
    if not tools:
        return EvalResult(value=1.0, comment="No tool calls")
    failed = [s.name for s in tools if s.status == "error"]
    rate = 1 - len(failed) / len(tools)
    return EvalResult(value=round(rate, 4), comment=f"Failed: {failed}" if failed else None)


def _signature(span: SpanView) -> str:
    return span.name + "\x00" + json.dumps(span.input, sort_keys=True, default=str)


def no_redundant_calls(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    """No tool was called twice with identical arguments (wasted work)."""
    seen: set[str] = set()
    repeated: list[str] = []
    for span in _tools(ctx):
        signature = _signature(span)
        if signature in seen and span.name not in repeated:
            repeated.append(span.name)
        seen.add(signature)
    return passed(not repeated, f"Repeated identical calls: {repeated}" if repeated else None)


def no_loops(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    """The same tool was not called more than `max_repeats` times in a row."""
    limit = int(config.get("max_repeats", 3))
    run_name, run_length, worst = None, 0, 0
    for span in _tools(ctx):
        run_length = run_length + 1 if span.name == run_name else 1
        run_name = span.name
        worst = max(worst, run_length)
        if run_length > limit:
            return passed(False, f"{span.name} called {run_length}+ times in a row")
    return passed(True, f"Longest run: {worst}")
