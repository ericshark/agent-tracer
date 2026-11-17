import { formatScore } from "../lib/format";
import type { Experiment, ItemScore } from "../lib/types";
import { scoreTone } from "./Scores";

const STATUS_STYLE: Record<Experiment["status"], string> = {
  pending: "text-ink-muted",
  running: "text-info",
  completed: "text-good",
  failed: "text-critical",
};

export function ExperimentStatus({ experiment }: { experiment: Experiment }) {
  const running = experiment.status === "running" || experiment.status === "pending";
  return (
    <span className={`mono inline-flex items-center gap-1.5 text-xs ${STATUS_STYLE[experiment.status]}`}>
      <span
        aria-hidden
        className={`h-1.5 w-1.5 rounded-full bg-current ${running ? "live-dot" : ""}`}
      />
      {experiment.status}
      {running && experiment.item_count > 0 && (
        <span className="text-ink-muted tabular-nums">
          {experiment.completed_count}/{experiment.item_count}
        </span>
      )}
    </span>
  );
}

/** Score value as a number for display: booleans become pass/fail text. */
export function scoreDisplay(score: ItemScore | undefined): {
  text: string;
  tone: string;
  title?: string;
} {
  if (!score) return { text: "—", tone: "text-ink-muted" };
  if (score.error) return { text: "n/a", tone: "text-ink-muted", title: score.error };
  if (typeof score.value === "boolean") {
    return {
      text: score.value ? "pass" : "fail",
      tone: score.value ? "text-good" : "text-critical",
      title: score.comment ?? undefined,
    };
  }
  return {
    text: formatScore(score.value),
    tone: scoreTone(score.value),
    title: score.comment ?? undefined,
  };
}

/** Horizontal 0–1 meter: one hue, magnitude only. The number carries the value. */
export function ScoreMeter({ label, mean, count }: { label: string; mean: number | null; count: number }) {
  const fraction = mean === null ? 0 : Math.max(0, Math.min(1, mean));
  return (
    <div className="min-w-0 bg-surface-1 px-4 py-3" title={`${label}: ${formatScore(mean)} over ${count}`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="mono truncate text-[11px] text-ink-muted">{label}</p>
        <p className="mono text-[15px] text-ink tabular-nums">{formatScore(mean)}</p>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div className="h-full rounded-full bg-accent" style={{ width: `${fraction * 100}%` }} />
      </div>
      <p className="mono mt-1.5 text-[10.5px] text-ink-muted tabular-nums">n = {count}</p>
    </div>
  );
}
