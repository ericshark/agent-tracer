"""Deterministic evaluators: no model call, same answer every time."""

import difflib
import re
from typing import Any

import jsonschema

from app.core.evals.base import (
    EvalConfigError,
    EvalContext,
    EvalResult,
    as_json,
    as_text,
    passed,
)


def _norm(text: str, config: dict[str, Any]) -> str:
    if config.get("strip", True):
        text = text.strip()
    if config.get("ignore_case", False):
        text = text.lower()
    return text


def _need_expected(ctx: EvalContext) -> None:
    if ctx.expected is None:
        raise EvalConfigError("This evaluator needs an expected output")


def exact_match(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    _need_expected(ctx)
    return passed(_norm(as_text(ctx.output), config) == _norm(as_text(ctx.expected), config))


def contains(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    needle = config.get("substring")
    if not needle:
        _need_expected(ctx)
        needle = as_text(ctx.expected)
    found = _norm(str(needle), config) in _norm(as_text(ctx.output), config)
    return passed(found, None if found else f"Output does not contain {str(needle)[:120]!r}")


def regex_match(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    pattern = config.get("pattern")
    if not pattern:
        raise EvalConfigError("`pattern` is required")
    try:
        compiled = re.compile(pattern, re.IGNORECASE if config.get("ignore_case") else 0)
    except re.error as exc:
        raise EvalConfigError(f"Invalid regular expression: {exc}") from exc
    return passed(compiled.search(as_text(ctx.output)) is not None)


def json_valid(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    try:
        as_json(ctx.output)
    except ValueError as exc:
        return passed(False, f"Not valid JSON: {exc}")
    return passed(True)


def json_schema(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    schema = config.get("schema")
    if not isinstance(schema, dict):
        raise EvalConfigError("`schema` must be a JSON Schema object")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise EvalConfigError(f"Invalid JSON Schema: {exc.message}") from exc
    try:
        value = as_json(ctx.output)
    except ValueError as exc:
        return passed(False, f"Not valid JSON: {exc}")
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path)
    )
    if not errors:
        return passed(True)
    first = errors[0]
    where = "/".join(str(p) for p in first.path) or "(root)"
    return passed(False, f"{where}: {first.message}"[:500])


def similarity(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    _need_expected(ctx)
    ratio = difflib.SequenceMatcher(
        None, _norm(as_text(ctx.output), config), _norm(as_text(ctx.expected), config)
    ).ratio()
    return EvalResult(value=round(ratio, 4))


def numeric_close(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    _need_expected(ctx)
    try:
        actual = float(as_text(ctx.output).strip())
        target = float(as_text(ctx.expected).strip())
    except ValueError:
        return passed(False, "Output or expected value is not a number")
    tolerance = float(config.get("tolerance", 1e-6))
    return passed(abs(actual - target) <= tolerance, f"|{actual} - {target}| vs {tolerance}")


def _budget(actual: float | None, config: dict[str, Any], key: str, unit: str) -> EvalResult:
    limit = config.get(key)
    if limit is None:
        raise EvalConfigError(f"`{key}` is required")
    if actual is None:
        raise EvalConfigError(f"No {unit} measurement is available for this run")
    return passed(actual <= float(limit), f"{actual:g} {unit} (limit {float(limit):g})")


def latency_under(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    return _budget(ctx.latency_ms, config, "max_ms", "ms")


def cost_under(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    return _budget(ctx.cost_usd, config, "max_usd", "USD")


def tokens_under(ctx: EvalContext, config: dict[str, Any]) -> EvalResult:
    return _budget(ctx.total_tokens, config, "max_tokens", "tokens")
