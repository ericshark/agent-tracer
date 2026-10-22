import { describe, expect, it } from "vitest";

import { percentile, relativeChange, summarizeAgents, windowDeltas } from "../lib/stats";
import type { StatsBucket, TraceSummary } from "../lib/types";

function bucket(partial: Partial<StatsBucket>): StatsBucket {
  return {
    bucket_start: "2026-01-01T00:00:00Z",
    trace_count: 0,
    error_count: 0,
    avg_duration_ms: null,
    total_tokens: 0,
    cost_usd: 0,
    ...partial,
  };
}

function trace(partial: Partial<TraceSummary>): TraceSummary {
  return {
    id: "t",
    trace_id: "abc",
    name: "agent",
    status: "ok",
    session_id: null,
    started_at: "2026-01-01T00:00:00Z",
    ended_at: null,
    duration_ms: 100,
    span_count: 1,
    error_count: 0,
    llm_call_count: 0,
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: 0,
    meta: null,
    ...partial,
  };
}

describe("relativeChange", () => {
  it("returns a fraction, or null without a baseline", () => {
    expect(relativeChange(100, 150)).toBeCloseTo(0.5);
    expect(relativeChange(0, 10)).toBeNull();
  });
});

describe("windowDeltas", () => {
  it("compares the second half of the window against the first", () => {
    const deltas = windowDeltas([
      bucket({ trace_count: 10, error_count: 2, avg_duration_ms: 200, cost_usd: 1 }),
      bucket({ trace_count: 10, error_count: 0, avg_duration_ms: 200, cost_usd: 1 }),
      bucket({ trace_count: 20, error_count: 1, avg_duration_ms: 100, cost_usd: 1 }),
      bucket({ trace_count: 10, error_count: 2, avg_duration_ms: 100, cost_usd: 3 }),
    ]);
    expect(deltas.traces).toBeCloseTo(0.5);
    expect(deltas.successPts).toBeCloseTo(0);
    expect(deltas.latency).toBeCloseTo(-0.5);
    expect(deltas.cost).toBeCloseTo(1);
  });

  it("yields nulls when there is nothing to compare", () => {
    expect(windowDeltas([bucket({ trace_count: 3 })]).traces).toBeNull();
    const empty = windowDeltas([bucket({}), bucket({ trace_count: 4 })]);
    expect(empty.traces).toBeNull();
    expect(empty.successPts).toBeNull();
  });
});

describe("percentile", () => {
  it("uses nearest-rank", () => {
    expect(percentile([], 95)).toBeNull();
    expect(percentile([5, 1, 3], 50)).toBe(3);
    expect(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95)).toBe(10);
  });
});

describe("summarizeAgents", () => {
  it("groups by trace name and ignores running traces in the success rate", () => {
    const agents = summarizeAgents([
      trace({ name: "router", status: "ok", cost_usd: 1 }),
      trace({ name: "router", status: "error", cost_usd: 3 }),
      trace({ name: "router", status: "running", started_at: "2026-01-02T00:00:00Z" }),
      trace({ name: "search", status: "ok" }),
    ]);
    expect(agents.map((a) => a.name)).toEqual(["router", "search"]);
    const router = agents[0];
    expect(router.runs).toBe(3);
    expect(router.successRate).toBeCloseTo(0.5);
    expect(router.totalCostUsd).toBeCloseTo(4);
  });
});
