"""Evaluator template catalog and the single entry point for running one."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.evals import builtin, judge, trajectory
from app.core.evals.base import EvalConfigError, EvalContext, EvalResult
from app.core.llm import Credentials, LLMConfigError


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # string | number | boolean | string_list | json | select
    description: str
    default: Any = None
    required: bool = False
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Template:
    key: str
    kind: str  # code | trajectory | llm_judge
    title: str
    description: str
    data_type: str  # numeric | boolean
    params: tuple[Param, ...] = ()
    needs_expected: bool = False
    needs_trace: bool = False
    run: Callable[[EvalContext, dict[str, Any]], EvalResult] | None = field(
        default=None, compare=False
    )


_TEXT_OPTS = (
    Param("ignore_case", "boolean", "Compare case-insensitively", default=False),
    Param("strip", "boolean", "Ignore leading/trailing whitespace", default=True),
)
_JUDGE_PARAMS = (Param("model", "string", "Judge model (defaults to the server's judge model)"),)

TEMPLATES: dict[str, Template] = {
    t.key: t
    for t in (
        # ------------------------------------------------------------ code
        Template(
            "exact_match",
            "code",
            "Exact match",
            "Output equals the expected output.",
            "boolean",
            params=_TEXT_OPTS,
            needs_expected=True,
            run=builtin.exact_match,
        ),
        Template(
            "contains",
            "code",
            "Contains",
            "Output contains a substring (or the expected output).",
            "boolean",
            params=(
                Param("substring", "string", "Text to look for; blank uses the expected output"),
                *_TEXT_OPTS,
            ),
            run=builtin.contains,
        ),
        Template(
            "regex_match",
            "code",
            "Regex match",
            "Output matches a regular expression.",
            "boolean",
            params=(
                Param("pattern", "string", "Regular expression", required=True),
                Param("ignore_case", "boolean", "Case-insensitive", default=False),
            ),
            run=builtin.regex_match,
        ),
        Template(
            "json_valid",
            "code",
            "Valid JSON",
            "Output parses as JSON.",
            "boolean",
            run=builtin.json_valid,
        ),
        Template(
            "json_schema",
            "code",
            "JSON schema",
            "Output is JSON that satisfies a JSON Schema.",
            "boolean",
            params=(Param("schema", "json", "JSON Schema object", required=True),),
            run=builtin.json_schema,
        ),
        Template(
            "similarity",
            "code",
            "Text similarity",
            "Character-level similarity to the expected output (0–1).",
            "numeric",
            params=_TEXT_OPTS,
            needs_expected=True,
            run=builtin.similarity,
        ),
        Template(
            "numeric_close",
            "code",
            "Numeric match",
            "Output is a number within a tolerance of the expected number.",
            "boolean",
            params=(Param("tolerance", "number", "Allowed absolute difference", default=1e-6),),
            needs_expected=True,
            run=builtin.numeric_close,
        ),
        Template(
            "latency_under",
            "code",
            "Latency budget",
            "The run finished within a time budget.",
            "boolean",
            params=(Param("max_ms", "number", "Maximum milliseconds", required=True),),
            run=builtin.latency_under,
        ),
        Template(
            "cost_under",
            "code",
            "Cost budget",
            "The run cost no more than a budget.",
            "boolean",
            params=(Param("max_usd", "number", "Maximum USD", required=True),),
            run=builtin.cost_under,
        ),
        Template(
            "tokens_under",
            "code",
            "Token budget",
            "The run used no more than a number of tokens.",
            "boolean",
            params=(Param("max_tokens", "number", "Maximum total tokens", required=True),),
            run=builtin.tokens_under,
        ),
        # ------------------------------------------------------ trajectory
        Template(
            "tool_sequence",
            "trajectory",
            "Tool sequence",
            "The agent called the expected tools (exact, in order, or any order).",
            "boolean",
            params=(
                Param(
                    "tools",
                    "string_list",
                    'Expected tool names; blank reads {"tools": [...]} from the test case',
                ),
                Param(
                    "mode",
                    "select",
                    "How strictly to compare",
                    default="in_order",
                    options=("exact", "in_order", "any_order"),
                ),
            ),
            needs_trace=True,
            run=trajectory.tool_sequence,
        ),
        Template(
            "required_tools",
            "trajectory",
            "Required tools",
            "Every listed tool was called at least once.",
            "boolean",
            params=(Param("tools", "string_list", "Tool names", required=True),),
            needs_trace=True,
            run=trajectory.required_tools,
        ),
        Template(
            "forbidden_tools",
            "trajectory",
            "Forbidden tools",
            "None of the listed tools was called.",
            "boolean",
            params=(Param("tools", "string_list", "Tool names", required=True),),
            needs_trace=True,
            run=trajectory.forbidden_tools,
        ),
        Template(
            "tool_args_match",
            "trajectory",
            "Tool arguments",
            "A call to a tool received specific argument values.",
            "boolean",
            params=(
                Param("tool", "string", "Tool name", required=True),
                Param("args", "json", "Argument values that must be present", required=True),
            ),
            needs_trace=True,
            run=trajectory.tool_args_match,
        ),
        Template(
            "max_steps",
            "trajectory",
            "Step budget",
            "The agent used no more than a number of model + tool steps.",
            "boolean",
            params=(Param("max", "number", "Maximum steps", required=True),),
            needs_trace=True,
            run=trajectory.max_steps,
        ),
        Template(
            "tool_success_rate",
            "trajectory",
            "Tool success rate",
            "Share of tool calls that succeeded (0–1).",
            "numeric",
            needs_trace=True,
            run=trajectory.tool_success_rate,
        ),
        Template(
            "no_redundant_calls",
            "trajectory",
            "No redundant calls",
            "No tool was called twice with identical arguments.",
            "boolean",
            needs_trace=True,
            run=trajectory.no_redundant_calls,
        ),
        Template(
            "no_loops",
            "trajectory",
            "No loops",
            "The same tool was not called many times in a row.",
            "boolean",
            params=(Param("max_repeats", "number", "Allowed consecutive calls", default=3),),
            needs_trace=True,
            run=trajectory.no_loops,
        ),
        # ------------------------------------------------------- llm judge
        Template(
            "correctness",
            "llm_judge",
            "Correctness",
            "A model judges whether the output agrees with the expected output.",
            "numeric",
            params=_JUDGE_PARAMS,
            needs_expected=True,
        ),
        Template(
            "faithfulness",
            "llm_judge",
            "Faithfulness",
            "A model judges whether the output is grounded in the input/context.",
            "numeric",
            params=_JUDGE_PARAMS,
        ),
        Template(
            "relevance",
            "llm_judge",
            "Relevance",
            "A model judges whether the output addresses the input.",
            "numeric",
            params=_JUDGE_PARAMS,
        ),
        Template(
            "helpfulness",
            "llm_judge",
            "Helpfulness",
            "A model judges how useful the output is to the person asking.",
            "numeric",
            params=_JUDGE_PARAMS,
        ),
        Template(
            "safety",
            "llm_judge",
            "Safety",
            "A model judges whether the output is free of harmful content.",
            "numeric",
            params=_JUDGE_PARAMS,
        ),
        Template(
            "task_completion",
            "llm_judge",
            "Task completion",
            "A model judges whether the agent finished the task, using its trajectory.",
            "numeric",
            params=_JUDGE_PARAMS,
        ),
        Template(
            "custom",
            "llm_judge",
            "Custom rubric",
            "A model grades the output against a rubric you write.",
            "numeric",
            params=(
                Param("rubric", "string", "What a good output looks like", required=True),
                *_JUDGE_PARAMS,
            ),
        ),
    )
}


def validate_config(template_key: str, config: dict[str, Any]) -> None:
    template = TEMPLATES.get(template_key)
    if template is None:
        raise EvalConfigError(f"Unknown evaluator template: {template_key}")
    known = {p.name for p in template.params} | {"provider"}
    unknown = sorted(set(config) - known)
    if unknown:
        raise EvalConfigError(f"Unknown settings for {template.title}: {', '.join(unknown)}")
    for param in template.params:
        value = config.get(param.name)
        if param.required and (value is None or value == "" or value == []):
            raise EvalConfigError(f"`{param.name}` is required for {template.title}")
        if value is not None and param.type == "select" and value not in param.options:
            raise EvalConfigError(f"`{param.name}` must be one of {list(param.options)}")


async def run_evaluator(
    template_key: str, config: dict[str, Any], ctx: EvalContext, creds: Credentials
) -> EvalResult:
    """Run one evaluator. Configuration and missing-data problems come back as
    `EvalResult.error`; only unexpected provider failures raise."""
    template = TEMPLATES.get(template_key)
    if template is None:
        return EvalResult(value=None, error=f"Unknown evaluator template: {template_key}")
    try:
        if template.kind == "llm_judge":
            result = await judge.run_judge(template_key, ctx, config, creds)
        else:
            assert template.run is not None
            result = template.run(ctx, config)
    except (EvalConfigError, LLMConfigError) as exc:
        return EvalResult(value=None, data_type=template.data_type, error=str(exc))
    if result.error is None and result.data_type != "boolean":
        result.data_type = template.data_type
    return result
