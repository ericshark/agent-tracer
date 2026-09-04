import { describe, expect, it } from "vitest";

import { buildSpanTree, flattenTree, pickDefaultSpan, timeExtent } from "../lib/spanTree";
import type { Span } from "../lib/types";

function span(overrides: Partial<Span>): Span {
  return {
    id: overrides.span_id ?? "x",
    span_id: "0000000000000001",
    parent_span_id: null,
    name: "span",
    kind: "CHAIN",
    status: "ok",
    started_at: "2026-08-04T12:00:00Z",
    ended_at: "2026-08-04T12:00:01Z",
    duration_ms: 1000,
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
    ...overrides,
  };
}

describe("buildSpanTree", () => {
  it("nests children under parents ordered by start time", () => {
    const spans = [
      span({ span_id: "aaaaaaaaaaaaaaaa", name: "root" }),
      span({
        span_id: "cccccccccccccccc",
        parent_span_id: "aaaaaaaaaaaaaaaa",
        name: "second",
        started_at: "2026-08-04T12:00:00.500Z",
      }),
      span({
        span_id: "bbbbbbbbbbbbbbbb",
        parent_span_id: "aaaaaaaaaaaaaaaa",
        name: "first",
        started_at: "2026-08-04T12:00:00.100Z",
      }),
    ];
    const roots = buildSpanTree(spans);
    expect(roots).toHaveLength(1);
    expect(roots[0].children.map((c) => c.span.name)).toEqual(["first", "second"]);
    expect(roots[0].children[0].depth).toBe(1);

    const flat = flattenTree(roots);
    expect(flat.map((n) => n.span.name)).toEqual(["root", "first", "second"]);
  });

  it("treats orphans as roots instead of dropping them", () => {
    const spans = [
      span({ span_id: "aaaaaaaaaaaaaaaa", name: "root" }),
      span({
        span_id: "dddddddddddddddd",
        parent_span_id: "ffffffffffffffff", // parent never arrived
        name: "orphan",
      }),
    ];
    const roots = buildSpanTree(spans);
    expect(roots.map((r) => r.span.name).sort()).toEqual(["orphan", "root"]);
  });
});

describe("pickDefaultSpan", () => {
  it("selects the innermost failure, not the propagated root error", () => {
    const spans = [
      span({ span_id: "aaaaaaaaaaaaaaaa", name: "agent", status: "error" }),
      span({
        span_id: "bbbbbbbbbbbbbbbb",
        parent_span_id: "aaaaaaaaaaaaaaaa",
        name: "failing-tool",
        status: "error",
        started_at: "2026-08-04T12:00:00.500Z",
      }),
    ];
    expect(pickDefaultSpan(spans)?.name).toBe("failing-tool");
  });

  it("picks the earliest failure when several are siblings", () => {
    const spans = [
      span({ span_id: "aaaaaaaaaaaaaaaa", name: "agent", status: "error" }),
      span({
        span_id: "cccccccccccccccc",
        parent_span_id: "aaaaaaaaaaaaaaaa",
        name: "second-failure",
        status: "error",
        started_at: "2026-08-04T12:00:02Z",
      }),
      span({
        span_id: "bbbbbbbbbbbbbbbb",
        parent_span_id: "aaaaaaaaaaaaaaaa",
        name: "first-failure",
        status: "error",
        started_at: "2026-08-04T12:00:01Z",
      }),
    ];
    expect(pickDefaultSpan(spans)?.name).toBe("first-failure");
  });

  it("falls back to the root span when nothing failed", () => {
    const spans = [
      span({
        span_id: "bbbbbbbbbbbbbbbb",
        parent_span_id: "aaaaaaaaaaaaaaaa",
        name: "child",
      }),
      span({ span_id: "aaaaaaaaaaaaaaaa", name: "root" }),
    ];
    expect(pickDefaultSpan(spans)?.name).toBe("root");
  });

  it("returns null for an empty trace", () => {
    expect(pickDefaultSpan([])).toBeNull();
  });
});

describe("timeExtent", () => {
  it("covers the full window and tolerates open spans", () => {
    const now = Date.parse("2026-08-04T12:00:05Z");
    const spans = [
      span({ started_at: "2026-08-04T12:00:00Z", ended_at: "2026-08-04T12:00:01Z" }),
      span({
        span_id: "eeeeeeeeeeeeeeee",
        started_at: "2026-08-04T12:00:02Z",
        ended_at: null,
      }),
    ];
    const extent = timeExtent(spans, now);
    expect(extent.start).toBe(Date.parse("2026-08-04T12:00:00Z"));
    expect(extent.end).toBe(now);
  });

  it("never returns a zero-width window", () => {
    const extent = timeExtent([]);
    expect(extent.end).toBeGreaterThan(extent.start);
  });
});
