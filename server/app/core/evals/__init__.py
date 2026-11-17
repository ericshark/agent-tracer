"""Evaluators: turn a recorded or freshly produced run into scores.

* base.py       — EvalContext / EvalResult and shared text helpers
* builtin.py    — deterministic checks (match, regex, JSON, budgets)
* trajectory.py — agent-specific checks over the span tree (tool use)
* judge.py      — LLM-as-judge rubrics
* registry.py   — the template catalog and the single `run_evaluator` entry point
"""
