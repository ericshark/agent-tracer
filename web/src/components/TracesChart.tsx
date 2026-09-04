import { useMemo, useState } from "react";

import { formatCost, formatDateTime, formatTokens } from "../lib/format";
import type { StatsBucket } from "../lib/types";
import { GhostButton } from "./ui";

const PLOT_HEIGHT = 150;
const PAD_TOP = 10; // keeps the top tick label inside the viewBox
const AXIS_BAND = 22;
const Y_LABEL_WIDTH = 34;

function niceMax(n: number): number {
  if (n <= 5) return Math.max(2, n);
  const magnitude = 10 ** Math.floor(Math.log10(n));
  for (const mult of [1, 2, 5, 10]) {
    if (n <= mult * magnitude) return mult * magnitude;
  }
  return 10 * magnitude;
}

/** Traces per time bucket, completed vs errored (stacked columns). */
export function TracesChart({ buckets }: { buckets: StatsBucket[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [tableView, setTableView] = useState(false);

  const maxCount = useMemo(
    () => niceMax(Math.max(1, ...buckets.map((b) => b.trace_count))),
    [buckets],
  );

  const width = 900; // viewBox units; scales responsively
  const plotWidth = width - Y_LABEL_WIDTH;
  const band = plotWidth / Math.max(1, buckets.length);
  const barWidth = Math.min(24, Math.max(3, band * 0.62));
  const yTicks = [0, maxCount / 2, maxCount];

  const scaleY = (count: number) => (count / maxCount) * PLOT_HEIGHT;

  if (tableView) {
    return (
      <div className="card p-4">
        <ChartHeader tableView={tableView} onToggle={() => setTableView(false)} />
        <div className="max-h-64 overflow-y-auto panel-scroll">
          <table className="w-full text-xs">
            <thead className="text-left text-ink-muted">
              <tr>
                <th className="py-1 pr-3 font-medium">Bucket</th>
                <th className="py-1 pr-3 text-right font-medium">Traces</th>
                <th className="py-1 pr-3 text-right font-medium">Errors</th>
                <th className="py-1 pr-3 text-right font-medium">Tokens</th>
                <th className="py-1 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {buckets.map((b) => (
                <tr key={b.bucket_start} className="border-t border-hairline">
                  <td className="py-1 pr-3 text-ink-secondary">
                    {formatDateTime(b.bucket_start)}
                  </td>
                  <td className="py-1 pr-3 text-right">{b.trace_count}</td>
                  <td className="py-1 pr-3 text-right">{b.error_count}</td>
                  <td className="py-1 pr-3 text-right">{formatTokens(b.total_tokens)}</td>
                  <td className="py-1 text-right">{formatCost(b.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  const hovered = hover !== null ? buckets[hover] : null;

  return (
    <div className="card relative p-4">
      <ChartHeader tableView={tableView} onToggle={() => setTableView(true)} />
      <svg
        viewBox={`0 0 ${width} ${PAD_TOP + PLOT_HEIGHT + AXIS_BAND}`}
        className="w-full"
        role="img"
        aria-label="Traces over time, completed versus errored"
        onMouseLeave={() => setHover(null)}
      >
        {/* hairline gridlines at clean ticks */}
        {yTicks.map((tick) => {
          const y = PAD_TOP + PLOT_HEIGHT - scaleY(tick);
          return (
            <g key={tick}>
              <line
                x1={Y_LABEL_WIDTH}
                x2={width}
                y1={y}
                y2={y}
                stroke={tick === 0 ? "var(--baseline)" : "var(--grid)"}
                strokeWidth={1}
              />
              <text
                x={Y_LABEL_WIDTH - 6}
                y={y + 3}
                textAnchor="end"
                className="tabular-nums"
                fontSize={10}
                fill="var(--text-muted)"
              >
                {tick}
              </text>
            </g>
          );
        })}

        {buckets.map((bucket, i) => {
          const x = Y_LABEL_WIDTH + i * band + (band - barWidth) / 2;
          const okCount = bucket.trace_count - bucket.error_count;
          const okH = scaleY(okCount);
          const errH = scaleY(bucket.error_count);
          const gap = okH > 0 && errH > 0 ? 2 : 0; // 2px surface gap between segments
          const errY = PAD_TOP + PLOT_HEIGHT - errH;
          const okY = PAD_TOP + PLOT_HEIGHT - errH - gap - okH;
          const radius = 4;
          return (
            <g key={bucket.bucket_start}>
              {/* error segment sits on the baseline (square bottom) */}
              {errH > 0 && (
                <path
                  d={
                    okH > 0
                      ? `M ${x} ${errY} H ${x + barWidth} V ${PAD_TOP + PLOT_HEIGHT} H ${x} Z`
                      : roundedTopBar(x, errY, barWidth, errH, radius)
                  }
                  fill="var(--status-critical)"
                />
              )}
              {/* completed segment with 4px rounded data-end */}
              {okH > 0 && <path d={roundedTopBar(x, okY, barWidth, okH, radius)} fill="var(--series-1)" />}
              {/* full-band hit target */}
              <rect
                x={Y_LABEL_WIDTH + i * band}
                y={0}
                width={band}
                height={PAD_TOP + PLOT_HEIGHT}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
              />
            </g>
          );
        })}

        {/* x-axis time labels: first, middle, last */}
        {buckets.length > 2 &&
          [0, Math.floor(buckets.length / 2), buckets.length - 1].map((i) => (
            <text
              key={i}
              x={Y_LABEL_WIDTH + i * band + band / 2}
              y={PAD_TOP + PLOT_HEIGHT + 15}
              textAnchor="middle"
              fontSize={10}
              fill="var(--text-muted)"
            >
              {formatDateTime(buckets[i].bucket_start)}
            </text>
          ))}
      </svg>

      {hovered && hover !== null && (
        <div
          className="pointer-events-none absolute top-12 z-10 rounded-md border border-hairline bg-surface-2 px-3 py-2 text-xs shadow-lg"
          style={{
            left: `${((Y_LABEL_WIDTH + (hover + 0.5) * band) / width) * 100}%`,
            transform: hover > buckets.length / 2 ? "translateX(-105%)" : "translateX(6px)",
          }}
        >
          <p className="font-medium">{formatDateTime(hovered.bucket_start)}</p>
          <p className="mt-1 text-ink-secondary">
            {hovered.trace_count} trace{hovered.trace_count === 1 ? "" : "s"} ·{" "}
            {hovered.error_count} error{hovered.error_count === 1 ? "" : "s"}
          </p>
          <p className="text-ink-muted">
            {formatTokens(hovered.total_tokens)} tokens · {formatCost(hovered.cost_usd)}
          </p>
        </div>
      )}
    </div>
  );
}

function roundedTopBar(x: number, y: number, w: number, h: number, r: number): string {
  const radius = Math.min(r, w / 2, h);
  return [
    `M ${x} ${y + h}`,
    `V ${y + radius}`,
    `Q ${x} ${y} ${x + radius} ${y}`,
    `H ${x + w - radius}`,
    `Q ${x + w} ${y} ${x + w} ${y + radius}`,
    `V ${y + h}`,
    "Z",
  ].join(" ");
}

function ChartHeader({ tableView, onToggle }: { tableView: boolean; onToggle: () => void }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <h3 className="text-sm font-medium">Traces over time</h3>
        <div className="flex items-center gap-3 text-[11px] text-ink-secondary">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-[2px]" style={{ background: "var(--series-1)" }} />
            Completed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-[2px]" style={{ background: "var(--status-critical)" }} />
            ✕ Errors
          </span>
        </div>
      </div>
      <GhostButton onClick={onToggle} className="!px-2 !py-0.5 text-xs">
        {tableView ? "Chart" : "Table"}
      </GhostButton>
    </div>
  );
}
