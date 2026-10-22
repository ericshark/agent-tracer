import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { formatCost, formatDuration, formatTimeAgo, formatTokens } from "../lib/format";
import type { TraceStatus, TraceSummary } from "../lib/types";
import { DotMeter, StatusBadge } from "./ui";

const STATUS_COLOR: Record<TraceStatus, string> = {
  ok: "var(--status-good)",
  error: "var(--status-critical)",
  running: "var(--status-info)",
};

export function TraceTable({
  traces,
  projectId,
  compareBase,
  onPickCompare,
  header,
}: {
  traces: TraceSummary[];
  projectId: string;
  compareBase?: string | null;
  onPickCompare?: (tracePk: string) => void;
  header?: ReactNode;
}) {
  // Duration bars are relative to the slowest trace in view.
  const maxDuration = useMemo(
    () => Math.max(1, ...traces.map((t) => t.duration_ms ?? 0)),
    [traces],
  );

  return (
    <div className="card">
      {header}
      <div className="overflow-x-auto rounded-b-[12px]">
        <table className="mono w-full min-w-[880px] text-[13px]">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-ink-secondary">
              <th className="px-5 py-2.5 font-medium">Trace</th>
              <th className="px-3 py-2.5 font-medium">Status</th>
              <th className="px-3 py-2.5 font-medium">Duration</th>
              <th className="px-3 py-2.5 text-right font-medium">Spans</th>
              <th className="px-3 py-2.5 text-right font-medium">Tokens</th>
              <th className="px-3 py-2.5 text-right font-medium">Cost</th>
              <th className="px-3 py-2.5 text-right font-medium">Started</th>
              {onPickCompare && <th className="px-5 py-2.5 text-right font-medium">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {traces.map((trace) => {
              const isBase = compareBase === trace.id;
              return (
                <tr
                  key={trace.id}
                  className={`border-b border-hairline transition-colors last:border-0 ${
                    isBase ? "bg-accent-soft" : "hover:bg-surface-2/60"
                  }`}
                >
                  <td className="px-5 py-2.5">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-hairline bg-surface-2 text-[11px] text-ink-secondary uppercase">
                        {trace.name.slice(0, 1)}
                      </span>
                      <div className="min-w-0">
                        <Link
                          to={`/projects/${projectId}/traces/${trace.id}`}
                          className="block max-w-[260px] truncate text-ink hover:text-accent"
                        >
                          {trace.name}
                        </Link>
                        <span className="block text-[10.5px] text-ink-muted">
                          {trace.trace_id.slice(0, 8)}
                          {trace.session_id && ` · ${trace.session_id}`}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={trace.status} />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <DotMeter
                        value={(trace.duration_ms ?? 0) / maxDuration}
                        color={STATUS_COLOR[trace.status]}
                        columns={36}
                        rows={4}
                        label={formatDuration(trace.duration_ms)}
                      />
                      <span className="w-14 text-[11px] text-ink-secondary tabular-nums">
                        {formatDuration(trace.duration_ms)}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right text-ink-secondary tabular-nums">
                    {trace.span_count}
                    {trace.llm_call_count > 0 && (
                      <span className="text-ink-muted"> · {trace.llm_call_count} llm</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right text-ink-secondary tabular-nums">
                    {formatTokens(trace.input_tokens + trace.output_tokens)}
                  </td>
                  <td className="px-3 py-2.5 text-right text-ink tabular-nums">
                    {formatCost(trace.cost_usd)}
                  </td>
                  <td
                    className="px-3 py-2.5 text-right text-xs text-ink-muted"
                    title={new Date(trace.started_at).toLocaleString()}
                  >
                    {formatTimeAgo(trace.started_at)}
                  </td>
                  {onPickCompare && (
                    <td className="px-5 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => onPickCompare(trace.id)}
                        className={`rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
                          isBase
                            ? "border-accent/60 text-accent"
                            : "border-hairline text-ink-muted hover:bg-surface-2 hover:text-ink"
                        }`}
                      >
                        {isBase ? "Base ✓" : compareBase ? "Compare ↔" : "Compare"}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
