"""Agent Tracer SDK — lightweight tracing for AI agents.

Quick start:

    from agent_tracer import AgentTracer

    tracer = AgentTracer(api_key="at_…", base_url="http://localhost:8000")

    with tracer.trace("support-run", session_id="user-42"):
        with tracer.agent("router"):
            with tracer.llm(model="claude-opus-5", messages=msgs) as llm:
                reply = call_model(msgs)
                llm.set_output(reply).set_usage(input_tokens=812, output_tokens=310)
"""

from .client import AgentTracer, current_span, current_trace
from .ids import new_span_id, new_trace_id
from .spans import SpanHandle, TraceHandle

__version__ = "0.1.0"

__all__ = [
    "AgentTracer",
    "SpanHandle",
    "TraceHandle",
    "__version__",
    "current_span",
    "current_trace",
    "new_span_id",
    "new_trace_id",
]
