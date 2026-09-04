import { Link } from "react-router-dom";

import { formatCost, formatDuration, formatTimeAgo, formatTokens } from "../lib/format";
import type { TraceSummary } from "../lib/types";
import { StatusBadge } from "./ui";

export function TraceTable({
  traces,
  projectId,
  compareBase,
  onPickCompare,
}: {
  traces: TraceSummary[];
  projectId: string;
  compareBase?: string | null;
  onPickCompare?: (tracePk: string) => void;
}) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-xs text-ink-muted">
            <th className="px-4 py-2.5 font-medium">Trace</th>
            <th className="px-3 py-2.5 font-medium">Status</th>
            <th className="px-3 py-2.5 text-right font-medium">Duration</th>
            <th className="px-3 py-2.5 text-right font-medium">Spans</th>
            <th className="px-3 py-2.5 text-right font-medium">LLM</th>
            <th className="px-3 py-2.5 text-right font-medium">Tokens</th>
            <th className="px-3 py-2.5 text-right font-medium">Cost</th>
            <th className="px-3 py-2.5 font-medium">Session</th>
            <th className="px-3 py-2.5 text-right font-medium">Started</th>
            {onPickCompare && <th className="px-3 py-2.5" />}
          </tr>
        </thead>
        <tbody>
          {traces.map((trace) => (
            <tr
              key={trace.id}
              className="border-b border-hairline transition-colors last:border-0 hover:bg-surface-2/60"
            >
              <td className="px-4 py-2.5">
                <Link
                  to={`/projects/${projectId}/traces/${trace.id}`}
                  className="font-medium hover:text-accent"
                >
                  {trace.name}
                </Link>
                <span className="mono ml-2 hidden text-[11px] text-ink-muted lg:inline">
                  {trace.trace_id.slice(0, 8)}
                </span>
              </td>
              <td className="px-3 py-2.5">
                <StatusBadge status={trace.status} />
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink-secondary">
                {formatDuration(trace.duration_ms)}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink-secondary">
                {trace.span_count}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink-secondary">
                {trace.llm_call_count}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink-secondary">
                {formatTokens(trace.input_tokens + trace.output_tokens)}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink-secondary">
                {formatCost(trace.cost_usd)}
              </td>
              <td className="px-3 py-2.5 text-xs text-ink-muted">{trace.session_id ?? "—"}</td>
              <td
                className="px-3 py-2.5 text-right text-xs text-ink-muted"
                title={new Date(trace.started_at).toLocaleString()}
              >
                {formatTimeAgo(trace.started_at)}
              </td>
              {onPickCompare && (
                <td className="px-3 py-2.5 text-right">
                  <button
                    type="button"
                    onClick={() => onPickCompare(trace.id)}
                    className={`rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
                      compareBase === trace.id
                        ? "border-accent bg-accent-soft text-accent"
                        : "border-hairline text-ink-muted hover:bg-surface-2"
                    }`}
                  >
                    {compareBase === trace.id ? "Base ✓" : "Compare"}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
