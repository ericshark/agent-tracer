import { useEffect, useRef, useState, type ReactNode } from "react";

import type { SpanKind, TraceStatus } from "../lib/types";
import { CloseIcon, SearchIcon } from "./icons";

/* ------------------------------------------------------------- status badge
   Status is never color-alone: icon + label always ride together. */

const STATUS_META: Record<TraceStatus, { label: string; icon: string; className: string }> = {
  ok: { label: "OK", icon: "✓", className: "text-good border-good/45 bg-good/10" },
  error: {
    label: "Error",
    icon: "✕",
    className: "text-critical border-critical/45 bg-critical/10",
  },
  running: { label: "Running", icon: "●", className: "text-info border-info/50 bg-info/10" },
};

export function StatusBadge({ status, compact }: { status: TraceStatus; compact?: boolean }) {
  const meta = STATUS_META[status];
  if (compact) {
    return (
      <span
        className={`inline-flex text-xs font-medium ${meta.className.split(" ")[0]}`}
        title={meta.label}
      >
        <span aria-hidden className={status === "running" ? "live-dot" : ""}>
          {meta.icon}
        </span>
      </span>
    );
  }
  return (
    <span
      className={`mono inline-flex min-w-[88px] items-center justify-center gap-1.5 rounded-full border px-2.5 py-[3px] text-[11px] font-medium ${meta.className}`}
      title={meta.label}
    >
      <span aria-hidden className={`text-[9px] ${status === "running" ? "live-dot" : ""}`}>
        {meta.icon}
      </span>
      {meta.label}
    </span>
  );
}

/* --------------------------------------------------------------- kind badge
   Fixed categorical slot per kind (color follows the entity, never rank). */

export const KIND_COLOR: Record<SpanKind, string> = {
  LLM: "var(--series-1)",
  TOOL: "var(--series-2)",
  AGENT: "var(--series-3)",
  CHAIN: "var(--series-4)",
  RETRIEVER: "var(--series-5)",
  EMBEDDING: "var(--series-6)",
  GUARDRAIL: "var(--series-7)",
  UNKNOWN: "var(--series-8)",
};

export function KindBadge({ kind }: { kind: SpanKind }) {
  return (
    <span className="mono inline-flex items-center gap-1.5 text-[10.5px] font-medium tracking-wide text-ink-secondary">
      <span
        aria-hidden
        className="inline-block h-2 w-2 rounded-[2px]"
        style={{ background: KIND_COLOR[kind] ?? KIND_COLOR.UNKNOWN }}
      />
      {kind}
    </span>
  );
}

/* ---------------------------------------------------------------- dot meter
   A dot-matrix progress bar. The boundary column is dithered so the fill
   edge reads as a soft fade rather than a hard stop. */

export function DotMeter({
  value,
  color = "var(--accent)",
  columns = 44,
  rows = 4,
  dot = 3,
  gap = 1,
  className,
  label,
}: {
  value: number;
  color?: string;
  columns?: number;
  rows?: number;
  dot?: number;
  gap?: number;
  className?: string;
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const filled = clamped * columns;
  const full = Math.floor(filled);
  const pitch = dot + gap;
  const cells: ReactNode[] = [];
  for (let c = 0; c < columns; c++) {
    for (let r = 0; r < rows; r++) {
      const isFull = c < full;
      // Dither the 1–2 columns at the boundary into a checkerboard.
      const isEdge = !isFull && c < Math.ceil(filled) + 1 && (c + r) % 2 === 0;
      cells.push(
        <rect
          key={`${c}-${r}`}
          x={c * pitch}
          y={r * pitch}
          width={dot}
          height={dot}
          rx={0.6}
          fill={isFull || isEdge ? color : "var(--dot-dim)"}
          opacity={isEdge ? 0.7 : 1}
        />,
      );
    }
  }
  return (
    <svg
      width={columns * pitch - gap}
      height={rows * pitch - gap}
      viewBox={`0 0 ${columns * pitch - gap} ${rows * pitch - gap}`}
      className={className}
      role="img"
      aria-label={label ?? `${Math.round(clamped * 100)}%`}
    >
      {cells}
    </svg>
  );
}

/* ---------------------------------------------------------------- icon chip */

export function IconChip({ children }: { children: ReactNode }) {
  return (
    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-accent/25 bg-accent-soft text-accent">
      {children}
    </span>
  );
}

/* -------------------------------------------------------------- copy button */

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="rounded-md border border-hairline bg-surface-1 px-2 py-1 text-xs text-ink-secondary transition-colors hover:bg-surface-2 hover:text-ink"
    >
      {copied ? "Copied ✓" : (label ?? "Copy")}
    </button>
  );
}

/* ------------------------------------------------------------------ spinner */

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="mono flex items-center gap-2 text-xs text-ink-muted" role="status">
      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-baseline border-t-accent" />
      {label ?? "Loading…"}
    </div>
  );
}

/* -------------------------------------------------------------- empty state */

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-14 text-center">
      <span aria-hidden className="dot-grid mb-2 h-10 w-24 rounded-md" />
      <p className="mono text-sm font-medium text-ink-secondary">{title}</p>
      {children && <div className="max-w-md text-sm text-ink-muted">{children}</div>}
    </div>
  );
}

/* -------------------------------------------------------------------- modal */

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[10vh] backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`card max-h-[80vh] w-full ${wide ? "max-w-3xl" : "max-w-lg"} overflow-y-auto p-5 shadow-2xl`}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="mono text-sm font-medium">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-ink-muted hover:bg-surface-2 hover:text-ink"
          >
            <CloseIcon size={14} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- menu
   Small popover anchored to a trigger; closes on outside click or Escape. */

export function Menu({
  trigger,
  children,
  align = "right",
  placement = "bottom",
  label,
  triggerClassName,
}: {
  trigger: ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  placement?: "bottom" | "top";
  label: string;
  triggerClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={triggerClassName}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute z-40 min-w-40 rounded-lg border border-hairline bg-surface-2 p-1 shadow-xl ${
            align === "right" ? "right-0" : "left-0"
          } ${placement === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5"}`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export function MenuItem({
  onSelect,
  active,
  children,
}: {
  onSelect: () => void;
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onSelect}
      className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-surface-3 ${
        active ? "text-accent" : "text-ink-secondary hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ buttons */

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className, ...rest } = props;
  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50 ${className ?? ""}`}
    />
  );
}

export function GhostButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className, ...rest } = props;
  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg border border-hairline bg-surface-2 px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-50 ${className ?? ""}`}
    />
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className, ...rest } = props;
  return (
    <input
      {...rest}
      className={`rounded-lg border border-hairline bg-surface-2 px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent/60 focus:outline-none ${className ?? ""}`}
    />
  );
}

export function SearchInput({ className, ...rest }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label
      className={`flex items-center gap-2 rounded-lg border border-hairline bg-surface-2 px-2.5 py-1.5 text-ink-muted focus-within:border-accent/60 ${className ?? ""}`}
    >
      <SearchIcon size={14} className="shrink-0" />
      <input
        type="search"
        {...rest}
        className="w-full min-w-0 bg-transparent text-xs text-ink placeholder:text-ink-muted focus:outline-none"
      />
    </label>
  );
}
