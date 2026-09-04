# agent-tracer-sdk

Lightweight Python tracing SDK for [Agent Tracer](../README.md) — instrument an
AI agent in a few lines and watch its executions live.

```bash
pip install agent-tracer-sdk        # from this repo: pip install -e sdk
```

```python
from agent_tracer import AgentTracer

tracer = AgentTracer(api_key="at_…", base_url="http://localhost:8000")

with tracer.trace("support-run", session_id="user-42"):
    with tracer.agent("router"):
        with tracer.llm(model="claude-opus-5", messages=msgs) as llm:
            reply = call_model(msgs)
            llm.set_output(reply).set_usage(input_tokens=812, output_tokens=310)

        with tracer.tool("search", input={"q": "refund policy"}) as tool:
            tool.set_output(results)

@tracer.observe(kind="TOOL")            # decorator form, sync or async
def lookup_order(order_id: str): ...
```

- Configuration via `AGENT_TRACER_API_KEY` / `AGENT_TRACER_BASE_URL` env vars.
- Span kinds: `agent`, `llm`, `tool`, `chain`, `retriever`, or generic
  `span(kind=…)`.
- Exceptions are recorded (type, message, stacktrace) and re-raised.
- Background batch exporter (daemon thread, retries with backoff) — never blocks
  your app; `tracer.flush()` before exit in short scripts.
- No-op when no API key is configured, so it is safe to leave in place.
- W3C-format trace/span ids; only dependency is `httpx`.

See [`examples/demo_agent.py`](examples/demo_agent.py) for a full runnable demo.
