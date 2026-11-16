import type { StatsBucket, TraceSummary } from "./types";

/* ------------------------------------------------------------ window deltas
   The stats endpoint returns one window of buckets, not a previous period, so
   trends compare the second half of the window against the first half. */

interface HalfTotals {
  traces: number;
  errors: number;
  cost: number;
  durationWeighted: number;
  durationCount: number;
}

function totals(buckets: StatsBucket[]): HalfTotals {
  const out: HalfTotals = { traces: 0, errors: 0, cost: 0, durationWeighted: 0, durationCount: 0 };
  for (const b of buckets) {
    out.traces += b.trace_count;
    out.errors += b.error_count;
    out.cost += b.cost_usd;
    if (b.avg_duration_ms !== null && b.trace_count > 0) {
      out.durationWeighted += b.avg_duration_ms * b.trace_count;
      out.durationCount += b.trace_count;
    }
  }
  return out;
}

/** Fractional change from `previous` to `current`; null when undefined. */
export function relativeChange(previous: number, current: number): number | null {
  if (!Number.isFinite(previous) || !Number.isFinite(current) || previous <= 0) return null;
  return (current - previous) / previous;
}

export interface WindowDeltas {
  /** Fractional change in trace volume. */
  traces: number | null;
  /** Change in success rate, in percentage points. */
  successPts: number | null;
  /** Fractional change in mean duration. */
  latency: number | null;
  /** Fractional change in spend. */
  cost: number | null;
}

export function windowDeltas(buckets: StatsBucket[]): WindowDeltas {
  if (buckets.length < 2) {
    return { traces: null, successPts: null, latency: null, cost: null };
  }
  const mid = Math.floor(buckets.length / 2);
  const first = totals(buckets.slice(0, mid));
  const second = totals(buckets.slice(mid));

  const successPts =
    first.traces > 0 && second.traces > 0
      ? (1 - second.errors / second.traces - (1 - first.errors / first.traces)) * 100
      : null;
  const latency =
    first.durationCount > 0 && second.durationCount > 0
      ? relativeChange(
          first.durationWeighted / first.durationCount,
          second.durationWeighted / second.durationCount,
        )
      : null;

  return {
    traces: relativeChange(first.traces, second.traces),
    successPts,
    latency,
    cost: relativeChange(first.cost, second.cost),
  };
}

/* --------------------------------------------------------- agent breakdown
   Traces are grouped by their root name, which is how the SDK names an agent
   run (`tracer.trace("support-run")`). */

export interface AgentSummary {
  name: string;
  runs: number;
  errors: number;
  successRate: number;
  p95DurationMs: number | null;
  avgCostUsd: number;
  totalCostUsd: number;
}

export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.min(sorted.length - 1, Math.max(0, rank))];
}

export function summarizeAgents(traces: TraceSummary[]): AgentSummary[] {
  const groups = new Map<string, TraceSummary[]>();
  for (const trace of traces) {
    const group = groups.get(trace.name);
    if (group) group.push(trace);
    else groups.set(trace.name, [trace]);
  }

  const out: AgentSummary[] = [];
  for (const [name, runs] of groups) {
    const finished = runs.filter((t) => t.status !== "running");
    const errors = runs.filter((t) => t.status === "error").length;
    const durations = runs.map((t) => t.duration_ms).filter((d): d is number => d !== null);
    const totalCost = runs.reduce((sum, t) => sum + t.cost_usd, 0);
    out.push({
      name,
      runs: runs.length,
      errors,
      successRate: finished.length > 0 ? 1 - errors / finished.length : 1,
      p95DurationMs: percentile(durations, 95),
      avgCostUsd: totalCost / runs.length,
      totalCostUsd: totalCost,
    });
  }
  return out.sort((a, b) => b.runs - a.runs || a.name.localeCompare(b.name));
}
