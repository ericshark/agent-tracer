import type { ReactNode } from "react";

import { ArrowDownIcon, ArrowUpIcon } from "./icons";
import { IconChip } from "./ui";

export interface StatDelta {
  text: string;
  direction: "up" | "down";
  /** Whether this movement is an improvement (drives the color). */
  good: boolean;
}

/** One card split into equal cells by hairlines that survive wrapping. */
export function KpiStrip({ children }: { children: ReactNode }) {
  return (
    <div className="card grid grid-cols-2 gap-px overflow-hidden bg-hairline xl:grid-cols-4">
      {children}
    </div>
  );
}

export function StatTile({
  label,
  value,
  sub,
  icon,
  delta,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  delta?: StatDelta | null;
}) {
  return (
    <div className="flex min-w-0 flex-col bg-surface-1 px-4 py-4 sm:px-5">
      <div className="flex items-center gap-2.5">
        {icon && <IconChip>{icon}</IconChip>}
        <p className="mono truncate text-[12px] text-ink-secondary sm:text-[13px]">{label}</p>
      </div>
      <p className="mono mt-3 text-[22px] leading-none font-medium tracking-tight text-ink tabular-nums sm:text-[28px]">
        {value}
      </p>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-x-2 gap-y-1 text-xs">
        <span className="truncate text-ink-muted">{sub}</span>
        {delta && (
          <span
            className={`mono inline-flex shrink-0 items-center gap-0.5 tabular-nums ${
              delta.good ? "text-good" : "text-critical"
            }`}
          >
            {delta.direction === "up" ? <ArrowUpIcon size={12} /> : <ArrowDownIcon size={12} />}
            {delta.text}
          </span>
        )}
      </div>
    </div>
  );
}

/** Compact label/value strip for trace headers. Six items fill every breakpoint. */
export function MetricRow({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <div className="card grid grid-cols-2 gap-px overflow-hidden bg-hairline sm:grid-cols-3 lg:grid-cols-6">
      {items.map((item) => (
        <div key={item.label} className="min-w-0 bg-surface-1 px-4 py-3">
          <p className="mono text-[11px] text-ink-muted">{item.label}</p>
          <p className="mono mt-1 truncate text-[15px] text-ink tabular-nums">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
