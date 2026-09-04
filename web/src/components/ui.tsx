import { useEffect, useState, type ReactNode } from "react";

import type { SpanKind, TraceStatus } from "../lib/types";

/* ------------------------------------------------------------- status badge
   Status is never color-alone: icon + label always ride together. */

const STATUS_META: Record<TraceStatus, { label: string; icon: string; className: string }> = {
  ok: { label: "OK", icon: "✓", className: "text-good" },
  error: { label: "Error", icon: "✕", className: "text-critical" },
  running: { label: "Running", icon: "●", className: "text-accent" },
};

export function StatusBadge({ status, compact }: { status: TraceStatus; compact?: boolean }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${meta.className}`}
      title={meta.label}
    >
      <span aria-hidden className={status === "running" ? "live-dot" : ""}>
        {meta.icon}
      </span>
      {!compact && meta.label}
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
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-ink-secondary">
      <span
        aria-hidden
        className="inline-block h-2 w-2 rounded-[2px]"
        style={{ background: KIND_COLOR[kind] ?? KIND_COLOR.UNKNOWN }}
      />
      {kind}
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
      className="rounded-md border border-hairline px-2 py-1 text-xs text-ink-secondary transition-colors hover:bg-surface-2"
    >
      {copied ? "Copied ✓" : (label ?? "Copy")}
    </button>
  );
}

/* ------------------------------------------------------------------ spinner */

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted" role="status">
      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-baseline border-t-accent" />
      {label ?? "Loading…"}
    </div>
  );
}

/* -------------------------------------------------------------- empty state */

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-14 text-center">
      <p className="text-sm font-medium text-ink-secondary">{title}</p>
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
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-[10vh]"
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
          <h2 className="text-sm font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-ink-muted hover:bg-surface-2 hover:text-ink"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ buttons */

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className, ...rest } = props;
  return (
    <button
      {...rest}
      className={`rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 ${className ?? ""}`}
    />
  );
}

export function GhostButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className, ...rest } = props;
  return (
    <button
      {...rest}
      className={`rounded-md border border-hairline px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50 ${className ?? ""}`}
    />
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className, ...rest } = props;
  return (
    <input
      {...rest}
      className={`rounded-md border border-hairline bg-surface-2 px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none ${className ?? ""}`}
    />
  );
}
