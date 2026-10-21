# agent-tracer-sdk

Python instrumentation for [Agent Tracer](../README.md). Wrap agent and tool
calls to record their inputs, outputs, timing, and errors.

## Run locally

Requires Python 3.9+ and a running Agent Tracer API. In an activated virtual
environment, from the repository root:

```bash
pip install -e sdk
export AGENT_TRACER_API_KEY='at_replace_with_your_key'
export AGENT_TRACER_BASE_URL=http://localhost:8001
```

Use the API key printed by seeding or create one in Settings → API keys.
Match the base URL to your API's port. Run this Python example:

```python
from agent_tracer import AgentTracer

tracer = AgentTracer()
try:
    with tracer.trace("example-run"):
        with tracer.tool("add", input={"a": 2, "b": 3}) as span:
            span.set_output(2 + 3)
finally:
    tracer.flush()
    tracer.shutdown()
```

## Useful commands

From the repository root, `python sdk/examples/demo_agent.py --runs 2 --fail`
sends simulated model and tool calls, including a failed run. No provider key
is needed. For tests, install `pip install -e 'sdk[dev]'`, then run
`cd sdk && python -m pytest -q`.

## How it works

Nested spans form a trace. A background exporter sends batches with retries;
flush before short scripts exit. Exceptions are recorded and re-raised.
Tracing is disabled when no API key is configured.

See the [SDK reference](../docs/reference.md#using-the-python-sdk) for model
calls, decorators, usage/cost recording, and additional span types.
