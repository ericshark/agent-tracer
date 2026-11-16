import { memo, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { formatCost, formatCount, formatDateTime, formatTokens } from "../lib/format";
import type { StatsBucket } from "../lib/types";
import { GhostButton } from "./ui";

const PLOT_HEIGHT = 190;
const PAD_TOP = 10; // keeps the top tick label inside the viewBox
const AXIS_BAND = 24;
const Y_LABEL_WIDTH = 34;
const PITCH = 6; // dot grid spacing, in px
const DOT = 3;

/** Tracks an element's content width so the chart draws at 1:1 pixel scale. */
function useElementWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.floor(entry.contentRect.width);
      if (next > 0) setWidth(next);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function niceMax(n: number): number {
  if (n <= 5) return Math.max(2, n);
  const magnitude = 10 ** Math.floor(Math.log10(n));
  for (const mult of [1, 2, 5, 10]) {
    if (n <= mult * magnitude) return mult * magnitude;
  }
  return 10 * magnitude;
}

function formatTick(n: number): string {
  return n >= 1000 ? `${n / 1000}k` : String(n);
}

/** Linear interpolation of a per-bucket series at an x position. */
function sampleAt(values: number[], centers: number[], x: number): number {
  if (values.length === 0) return 0;
  if (x <= centers[0]) return values[0];
  for (let i = 1; i < centers.length; i++) {
    if (x <= centers[i]) {
      const t = (x - centers[i - 1]) / (centers[i] - centers[i - 1]);
      return values[i - 1] + t * (values[i] - values[i - 1]);
    }
  }
  return values[values.length - 1];
}

/**
 * Traces per time bucket as a dot-matrix area: green dots up to the total,
 * red dots for the errored share at the bottom, and a line along the top.
 */
export function TracesChart({
  buckets,
  title = "Trace Volume",
  controls,
}: {
  buckets: StatsBucket[];
  title?: string;
  controls?: ReactNode;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [tableView, setTableView] = useState(false);
  const [plotRef, width] = useElementWidth<HTMLDivElement>(600);

  const total = useMemo(() => buckets.reduce((sum, b) => sum + b.trace_count, 0), [buckets]);
  const errors = useMemo(() => buckets.reduce((sum, b) => sum + b.error_count, 0), [buckets]);
  const maxCount = useMemo(
    () => niceMax(Math.max(1, ...buckets.map((b) => b.trace_count))),
    [buckets],
  );

  const plotWidth = width - Y_LABEL_WIDTH;
  const band = plotWidth / Math.max(1, buckets.length);
  const centers = useMemo(
    () => buckets.map((_, i) => Y_LABEL_WIDTH + (i + 0.5) * band),
    [buckets, band],
  );
  const scaleY = (count: number) => (count / maxCount) * PLOT_HEIGHT;
  const baseY = PAD_TOP + PLOT_HEIGHT;

  const linePath = useMemo(() => {
    if (buckets.length === 0) return "";
    const pts = buckets.map(
      (b, i) =>
        `${centers[i].toFixed(1)} ${(baseY - (b.trace_count / maxCount) * PLOT_HEIGHT).toFixed(1)}`,
    );
    // Extend flat to both plot edges so the line spans the full width.
    const first = pts[0].split(" ")[1];
    const last = pts[pts.length - 1].split(" ")[1];
    return `M ${Y_LABEL_WIDTH} ${first} L ${pts.join(" L ")} L ${width} ${last}`;
  }, [buckets, centers, maxCount, baseY, width]);

  const spanHours =
    buckets.length > 1
      ? (new Date(buckets[buckets.length - 1].bucket_start).getTime() -
          new Date(buckets[0].bucket_start).getTime()) /
        3_600_000
      : 0;
  const formatX = (iso: string) =>
    spanHours <= 36
      ? new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
      : new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const xLabelCount = Math.min(buckets.length, Math.max(2, Math.floor(plotWidth / 90)));
  const xLabelIdx =
    xLabelCount > 1
      ? Array.from({ length: xLabelCount }, (_, k) =>
          Math.round((k * (buckets.length - 1)) / (xLabelCount - 1)),
        )
      : [];

  const yTicks = [0, maxCount / 2, maxCount];
  const hovered = hover !== null ? buckets[hover] : null;

  const header = (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div>
        <h3 className="mono text-[13px] text-ink-secondary">{title}</h3>
        <p className="mono mt-2 text-[28px] leading-none font-medium tracking-tight text-ink tabular-nums">
          {total.toLocaleString()}
        </p>
        <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-[2px] bg-accent" />
            Completed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-[2px] bg-critical" />✕ Errors ·{" "}
            {formatCount(errors)}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {controls}
        <GhostButton
          onClick={() => setTableView((v) => !v)}
          className="!px-2.5 !py-1 text-xs"
          aria-pressed={tableView}
        >
          {tableView ? "Chart" : "Table"}
        </GhostButton>
      </div>
    </div>
  );

  if (tableView) {
    return (
      <div className="card h-full p-5">
        {header}
        <div className="panel-scroll max-h-64 overflow-y-auto">
          <table className="mono w-full text-xs">
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
                  <td className="py-1 pr-3 text-ink-secondary">{formatDateTime(b.bucket_start)}</td>
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

  return (
    <div className="card relative h-full p-5">
      {header}
      <div ref={plotRef} className="relative">
        <svg
          width={width}
          height={PAD_TOP + PLOT_HEIGHT + AXIS_BAND}
          viewBox={`0 0 ${width} ${PAD_TOP + PLOT_HEIGHT + AXIS_BAND}`}
          className="block w-full"
          role="img"
          aria-label="Traces over time, completed versus errored"
          onMouseLeave={() => setHover(null)}
        >
          {yTicks.map((tick) => {
            const y = baseY - scaleY(tick);
            return (
              <g key={tick}>
                <line
                  x1={Y_LABEL_WIDTH}
                  x2={width}
                  y1={y}
                  y2={y}
                  stroke="var(--grid)"
                  strokeDasharray={tick === 0 ? undefined : "2 4"}
                />
                <text
                  x={Y_LABEL_WIDTH - 8}
                  y={y + 3}
                  textAnchor="end"
                  fontSize={10}
                  fontFamily="var(--font-mono)"
                  fill="var(--text-muted)"
                >
                  {formatTick(tick)}
                </text>
              </g>
            );
          })}

          <DotField buckets={buckets} centers={centers} maxCount={maxCount} width={width} />

          <path
            d={linePath}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={1.6}
            strokeLinejoin="round"
          />

          {hover !== null && hovered && (
            <g pointerEvents="none">
              <line
                x1={centers[hover]}
                x2={centers[hover]}
                y1={PAD_TOP}
                y2={baseY}
                stroke="var(--text-muted)"
                strokeDasharray="2 3"
              />
              <rect
                x={centers[hover] - 4}
                y={baseY - scaleY(hovered.trace_count) - 4}
                width={8}
                height={8}
                fill="var(--accent)"
                stroke="var(--surface-1)"
                strokeWidth={2}
              />
            </g>
          )}

          {buckets.map((bucket, i) => (
            <rect
              key={bucket.bucket_start}
              x={Y_LABEL_WIDTH + i * band}
              y={0}
              width={band}
              height={baseY}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}

          {xLabelIdx.map((i, k) => (
            <text
              key={i}
              x={centers[i]}
              y={baseY + 17}
              textAnchor={k === 0 ? "start" : k === xLabelIdx.length - 1 ? "end" : "middle"}
              fontSize={10}
              fontFamily="var(--font-mono)"
              fill="var(--text-secondary)"
            >
              {formatX(buckets[i].bucket_start)}
            </text>
          ))}
        </svg>

        {hovered && hover !== null && (
          <div
            className="pointer-events-none absolute top-2 z-10 rounded-lg border border-hairline bg-surface-2 px-3 py-2 text-xs whitespace-nowrap shadow-xl"
            style={{
              left: centers[hover],
              transform: hover > buckets.length / 2 ? "translateX(-110%)" : "translateX(12px)",
            }}
          >
            <p className="mono font-medium text-ink">{formatDateTime(hovered.bucket_start)}</p>
            <p className="mono mt-1 flex gap-3 text-ink-secondary tabular-nums">
              <span>{hovered.trace_count} traces</span>
              <span className={hovered.error_count ? "text-critical" : ""}>
                {hovered.error_count} err
              </span>
            </p>
            <p className="mono text-ink-muted tabular-nums">
              {formatTokens(hovered.total_tokens)} tok · {formatCost(hovered.cost_usd)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/** The dot grid is the expensive part; memoized so hover doesn't redraw it. */
const DotField = memo(function DotField({
  buckets,
  centers,
  maxCount,
  width,
}: {
  buckets: StatsBucket[];
  centers: number[];
  maxCount: number;
  width: number;
}) {
  const dots = useMemo(() => {
    const totals = buckets.map((b) => b.trace_count);
    const errs = buckets.map((b) => b.error_count);
    const rows = Math.floor(PLOT_HEIGHT / PITCH);
    const out: ReactNode[] = [];
    for (let x = Y_LABEL_WIDTH + PITCH / 2; x < width; x += PITCH) {
      const level = (sampleAt(totals, centers, x) / maxCount) * rows;
      const errLevel = (sampleAt(errs, centers, x) / maxCount) * rows;
      const col = Math.round(x / PITCH);
      for (let r = 0; r < rows && r < level; r++) {
        const depth = r / Math.max(level, 1); // 0 at baseline → 1 at the line
        // Thin the lower part of the area into a checkerboard fade.
        if (depth < 0.45 && (col + r) % 2 === 1) continue;
        const isError = r < errLevel;
        out.push(
          <rect
            key={`${col}-${r}`}
            x={x - DOT / 2}
            y={PAD_TOP + PLOT_HEIGHT - (r + 1) * PITCH + (PITCH - DOT) / 2}
            width={DOT}
            height={DOT}
            rx={0.5}
            fill={isError ? "var(--status-critical)" : "var(--accent)"}
            opacity={isError ? 0.95 : 0.35 + 0.6 * depth}
          />,
        );
      }
    }
    return out;
  }, [buckets, centers, maxCount, width]);

  return <g aria-hidden>{dots}</g>;
});
