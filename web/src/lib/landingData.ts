import type { Span, SpanKind, StatsBucket, TraceStatus, TraceSummary } from "./types";

/** Static sample data for the public landing page (modelled on the seeded demo). */

const BASE = Date.UTC(2026, 0, 15, 9, 0, 0);
const iso = (offsetMs: number) => new Date(BASE + offsetMs).toISOString();

/* ------------------------------------------------------------ volume chart */

const VOLUME = [
  14, 18, 16, 22, 27, 25, 31, 38, 34, 41, 46, 43, 52, 49, 58, 55, 63, 60, 68, 72, 66, 74, 79, 84,
];
const ERRORS = [0, 1, 0, 1, 1, 0, 2, 1, 1, 2, 1, 1, 3, 1, 2, 2, 2, 1, 3, 2, 4, 2, 3, 2];

export const LANDING_BUCKETS: StatsBucket[] = VOLUME.map((count, i) => ({
  bucket_start: new Date(BASE + i * 3_600_000).toISOString(),
  trace_count: count,
  error_count: ERRORS[i],
  avg_duration_ms: 2100 + ((i * 137) % 900),
  total_tokens: count * 3400,
  cost_usd: count * 0.0112,
}));

/* ----------------------------------------------------------------- traces */

interface Row {
  name: string;
  runs: number;
  errors: number;
  duration: number;
  cost: number;
}

const AGENTS: Row[] = [
  { name: "travel-concierge", runs: 9, errors: 0, duration: 4200, cost: 0.041 },
  { name: "support-triage", runs: 6, errors: 1, duration: 2600, cost: 0.018 },
  { name: "research-assistant", runs: 5, errors: 1, duration: 9800, cost: 0.092 },
  { name: "code-reviewer", runs: 4, errors: 2, duration: 6100, cost: 0.067 },
];

export const LANDING_TRACES: TraceSummary[] = AGENTS.flatMap((agent, a) =>
  Array.from({ length: agent.runs }, (_, i): TraceSummary => {
    const status: TraceStatus = i < agent.errors ? "error" : "ok";
    const start = a * 1_000_000 + i * 120_000;
    const duration = agent.duration + i * 90;
    return {
      id: `landing-${a}-${i}`,
      trace_id: `${a}${i}`.padStart(32, "0"),
      name: agent.name,
      status,
      session_id: null,
      started_at: iso(start),
      ended_at: iso(start + duration),
      duration_ms: duration,
      span_count: 6 + i,
      error_count: status === "error" ? 1 : 0,
      llm_call_count: 2,
      input_tokens: 2400,
      output_tokens: 620,
      cost_usd: agent.cost,
      meta: null,
    };
  }),
);

/* ------------------------------------------------------------- span tree */

function span(
  id: string,
  parent: string | null,
  name: string,
  kind: SpanKind,
  start: number,
  duration: number,
  extra: Partial<Span> = {},
): Span {
  return {
    id,
    span_id: id,
    parent_span_id: parent,
    name,
    kind,
    status: "ok",
    started_at: iso(start),
    ended_at: iso(start + duration),
    duration_ms: duration,
    input: null,
    output: null,
    attributes: null,
    events: null,
    model: null,
    input_tokens: null,
    output_tokens: null,
    cost_usd: null,
    error_type: null,
    error_message: null,
    error_stacktrace: null,
    ...extra,
  };
}

export const LANDING_SPANS: Span[] = [
  span("s1", null, "travel-concierge", "AGENT", 0, 5200, {
    input: { request: "Book a 3-night trip to Lisbon under $1,500" },
    output: { summary: "Found 2 options; hotel booking needs a retry." },
  }),
  span("s2", "s1", "plan_trip", "LLM", 80, 1300, {
    model: "claude-sonnet-5-5",
    input: [
      { role: "system", content: "You are a travel concierge. Use tools to find flights and hotels." },
      { role: "user", content: "Book a 3-night trip to Lisbon under $1,500." },
    ],
    output: {
      role: "assistant",
      content: "I'll search flights first, then look up hotels near Baixa.",
    },
    input_tokens: 412,
    output_tokens: 96,
    cost_usd: 0.0027,
  }),
  span("s3", "s1", "search_flights", "TOOL", 1450, 900, {
    input: { origin: "JFK", destination: "LIS", nights: 3 },
    output: { options: 2, cheapest_usd: 612 },
  }),
  span("s4", "s1", "retrieve_policies", "RETRIEVER", 1500, 520, {
    input: { query: "refund policy for hotel bookings" },
    output: { documents: 3 },
  }),
  span("s5", "s1", "check_budget", "GUARDRAIL", 2450, 240, {
    input: { total_usd: 1380, limit_usd: 1500 },
    output: { allowed: true },
  }),
  span("s6", "s1", "book_hotel", "TOOL", 2750, 1800, {
    status: "error",
    input: { hotel_id: "lis-baixa-204", nights: 3 },
    error_type: "TimeoutError",
    error_message: "Hotel provider did not respond within 1500ms",
    error_stacktrace:
      'Traceback (most recent call last):\n  File "tools/hotels.py", line 41, in book_hotel\n    resp = client.post(url, timeout=1.5)\nTimeoutError: Hotel provider did not respond within 1500ms',
  }),
  span("s7", "s1", "summarize", "LLM", 4600, 560, {
    model: "claude-sonnet-5-5",
    input: [{ role: "user", content: "Summarize the booking outcome." }],
    output: { role: "assistant", content: "Found 2 options; hotel booking needs a retry." },
    input_tokens: 388,
    output_tokens: 41,
    cost_usd: 0.0018,
  }),
];

export const SDK_SNIPPET = `from agent_tracer import AgentTracer

tracer = AgentTracer()  # reads AGENT_TRACER_API_KEY

with tracer.trace("travel-concierge"):
    with tracer.llm(model="claude-sonnet-5-5", messages=messages) as llm:
        reply = call_model(messages)
        llm.set_output({"role": "assistant", "content": reply.text})
        llm.set_usage(input_tokens=412, output_tokens=96)

    with tracer.tool("search_flights", input={"to": "LIS"}) as tool:
        tool.set_output(search_flights("LIS"))

tracer.flush()`;
