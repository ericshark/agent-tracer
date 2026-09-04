"""Live demo: a simulated research agent instrumented with the Agent Tracer SDK.

Run it against a running Agent Tracer server and watch the trace appear span
by span in the UI (Traces → the newest "research-agent" run):

    export AGENT_TRACER_API_KEY=at_…          # from Settings → API keys, or the seed output
    export AGENT_TRACER_BASE_URL=http://localhost:8000
    python examples/demo_agent.py             # one successful run
    python examples/demo_agent.py --fail      # a run that fails at the tool step
    python examples/demo_agent.py --runs 3    # several runs back to back

No model provider keys are needed — the "model" here is simulated, but the
instrumentation is exactly what you would wrap around real calls.
"""

import argparse
import random
import sys
import time

from agent_tracer import AgentTracer

QUESTION = "What changed in our checkout conversion after the March release?"


def fake_llm(prompt_tokens: int) -> tuple[str, int]:
    """Stand-in for a real model call."""
    time.sleep(random.uniform(0.8, 2.0))
    completion = (
        "Based on the retrieved dashboards, conversion dipped 4.2% in the week "
        "after the release, concentrated on mobile Safari. The A/B flag "
        "`new-payment-form` correlates with the drop."
    )
    return completion, len(completion) // 4


def run_once(tracer: AgentTracer, fail: bool) -> None:
    session = f"demo-{random.randint(100, 999)}"
    with tracer.trace("research-agent", session_id=session, metadata={"demo": True}):
        with tracer.agent("research-agent", input={"question": QUESTION}) as root:
            # Step 1 — plan with an LLM call
            with tracer.llm(
                model="claude-opus-5",
                name="plan",
                system="You are a data-savvy research agent. Plan before acting.",
                messages=[{"role": "user", "content": QUESTION}],
            ) as llm:
                text, out_tokens = fake_llm(prompt_tokens=740)
                plan = {"role": "assistant", "content": "Plan: query metrics, then summarize."}
                llm.set_output(plan)
                llm.set_usage(input_tokens=740, output_tokens=96)

            # Step 2 — hit an internal tool
            with tracer.tool(
                "query_metrics",
                input={"metric": "checkout_conversion", "window": "28d"},
            ) as tool:
                time.sleep(random.uniform(0.5, 1.2))
                if fail:
                    tool.add_event("retry", {"attempt": 1})
                    time.sleep(0.4)
                    raise TimeoutError("metrics-api: query exceeded 10s deadline")
                tool.set_output({"series": [[1, 0.031], [2, 0.029], [3, 0.027]]})

            # Step 3 — retrieve release notes
            with tracer.retriever(
                "search_release_notes", input={"query": "March release checkout"}
            ) as ret:
                time.sleep(random.uniform(0.2, 0.6))
                ret.set_output(
                    {"documents": [{"id": "rel-2026-03", "score": 0.93}]}
                )

            # Step 4 — compose the final answer
            with tracer.llm(
                model="claude-sonnet-5",
                name="compose-answer",
                messages=[
                    {"role": "user", "content": QUESTION},
                    {"role": "user", "content": "Context: metrics series + release notes."},
                ],
            ) as llm:
                answer, out_tokens = fake_llm(prompt_tokens=1900)
                llm.set_output({"role": "assistant", "content": answer})
                llm.set_usage(input_tokens=1900, output_tokens=out_tokens)

            root.set_output({"answer": "delivered"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fail", action="store_true", help="fail at the tool step")
    parser.add_argument("--runs", type=int, default=1, help="number of runs")
    args = parser.parse_args()

    tracer = AgentTracer()  # reads AGENT_TRACER_API_KEY / AGENT_TRACER_BASE_URL

    for i in range(args.runs):
        fail = args.fail and i == args.runs - 1
        print(f"▶ run {i + 1}/{args.runs}" + (" (will fail)" if fail else ""))
        try:
            run_once(tracer, fail)
            print("  ✓ completed")
        except TimeoutError as exc:
            print(f"  ✗ failed as requested: {exc}")
    tracer.flush()
    tracer.shutdown()
    print("Done — open the project in Agent Tracer to inspect the run(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
