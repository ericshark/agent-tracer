import { useMemo } from "react";

import { formatCost, formatDuration, formatPercent } from "../lib/format";
import { summarizeAgents } from "../lib/stats";
import type { TraceSummary } from "../lib/types";
import { DotMeter, GhostButton } from "./ui";

const MAX_ROWS = 6;

export function successColor(rate: number): string {
  if (rate >= 0.95) return "var(--status-good)";
  if (rate >= 0.8) return "var(--status-warning)";
  return "var(--status-critical)";
}

/** Per-agent health, aggregated from the currently loaded traces. */
export function AgentBreakdown({
  traces,
  onViewAll,
}: {
  traces: TraceSummary[];
  onViewAll?: () => void;
}) {
  const agents = useMemo(() => summarizeAgents(traces), [traces]);
  const shown = agents.slice(0, MAX_ROWS);

  return (
    <div className="card flex h-full flex-col p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="mono text-[13px] text-ink-secondary">Agents</h3>
          <p className="mono mt-2 text-[28px] leading-none font-medium tracking-tight text-ink tabular-nums">
            {agents.length}
          </p>
          <p className="mt-2 text-[11px] text-ink-muted">
            across the {traces.length} most recent traces
          </p>
        </div>
        {onViewAll && (
          <GhostButton onClick={onViewAll} className="!px-2.5 !py-1 text-xs">
            View all
          </GhostButton>
        )}
      </div>

      {shown.length === 0 ? (
        <div className="dot-grid grid flex-1 place-items-center rounded-lg text-xs text-ink-muted">
          No agent runs yet
        </div>
      ) : (
        <ul className="flex flex-col">
          {shown.map((agent) => (
            <li
              key={agent.name}
              className="flex items-center justify-between gap-4 border-t border-hairline py-2.5 first:border-t-0"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <span className="mono grid h-7 w-7 shrink-0 place-items-center rounded-md border border-hairline bg-surface-2 text-[11px] text-ink-secondary uppercase">
                  {agent.name.slice(0, 2)}
                </span>
                <div className="min-w-0">
                  <p className="mono truncate text-[13px] text-ink" title={agent.name}>
                    {agent.name}
                  </p>
                  <p className="mono text-[10.5px] text-ink-muted tabular-nums">
                    {agent.runs} run{agent.runs === 1 ? "" : "s"} · p95{" "}
                    {formatDuration(agent.p95DurationMs)} · {formatCost(agent.avgCostUsd)}/run
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <DotMeter
                  value={agent.successRate}
                  color={successColor(agent.successRate)}
                  columns={22}
                  rows={3}
                  label={`${formatPercent(agent.successRate)} success`}
                />
                <span className="mono w-11 text-right text-[11px] text-ink-secondary tabular-nums">
                  {formatPercent(agent.successRate)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
