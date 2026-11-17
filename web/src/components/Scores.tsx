import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { formatScore, formatTimeAgo } from "../lib/format";
import type { Score } from "../lib/types";
import { GhostButton, PrimaryButton, Spinner, TextInput } from "./ui";

/**
 * Tone for a score value. Only 0–1 values get a judgement color; anything else
 * (labels, counts, arbitrary scales) stays neutral rather than guessing.
 */
export function scoreTone(value: number | string | null | undefined): string {
  if (typeof value !== "number" || value < 0 || value > 1) return "text-ink-secondary";
  if (value >= 0.8) return "text-good";
  if (value >= 0.5) return "text-warning";
  return "text-critical";
}

export function ScoreChip({
  name,
  value,
}: {
  name: string;
  value: number | string | null | undefined;
}) {
  return (
    <span
      className="mono inline-flex max-w-[180px] items-center gap-1.5 rounded-md border border-hairline bg-surface-2 px-1.5 py-0.5 text-[10.5px]"
      title={`${name}: ${formatScore(value)}`}
    >
      <span className="truncate text-ink-muted">{name}</span>
      <span className={`shrink-0 tabular-nums ${scoreTone(value)}`}>{formatScore(value)}</span>
    </span>
  );
}

/** Up to `max` chips, then a "+n" overflow marker. */
export function ScoreChips({
  scores,
  max = 3,
}: {
  scores: Record<string, number | string> | null | undefined;
  max?: number;
}) {
  const entries = Object.entries(scores ?? {});
  if (entries.length === 0) return <span className="text-ink-muted">—</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {entries.slice(0, max).map(([name, value]) => (
        <ScoreChip key={name} name={name} value={value} />
      ))}
      {entries.length > max && (
        <span className="mono text-[10.5px] text-ink-muted">+{entries.length - max}</span>
      )}
    </span>
  );
}

const SOURCE_LABEL: Record<Score["source"], string> = {
  sdk: "SDK",
  api: "API",
  human: "Human",
  evaluator: "Evaluator",
};

function parseValue(raw: string): number | boolean | string {
  const trimmed = raw.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  const asNumber = Number(trimmed);
  return trimmed !== "" && Number.isFinite(asNumber) ? asNumber : trimmed;
}

/** Scores for a trace, optionally narrowed to one span, with an annotate form. */
export function ScoresPanel({
  tracePk,
  spanPk,
  readOnly,
}: {
  tracePk: string;
  spanPk?: string | null;
  readOnly?: boolean;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("quality");
  const [value, setValue] = useState("");
  const [comment, setComment] = useState("");

  const scores = useQuery({
    queryKey: ["scores", tracePk],
    queryFn: () => api.listScores(tracePk),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["scores", tracePk] });
    void queryClient.invalidateQueries({ queryKey: ["trace", tracePk] });
  };

  const create = useMutation({
    mutationFn: (override?: number | boolean) =>
      api.createScore(tracePk, {
        name: name.trim(),
        value: override ?? parseValue(value),
        span_pk: spanPk ?? null,
        comment: comment.trim() || undefined,
      }),
    onSuccess: () => {
      setValue("");
      setComment("");
      refresh();
    },
  });

  const remove = useMutation({
    mutationFn: (scoreId: string) => api.deleteScore(scoreId),
    onSuccess: refresh,
  });

  const shown = (scores.data ?? []).filter((s) => (spanPk ? s.span_pk === spanPk : true));
  const canSubmit = name.trim() !== "" && value.trim() !== "" && !create.isPending;

  return (
    <div className="flex flex-col gap-4">
      {scores.isLoading ? (
        <Spinner />
      ) : shown.length === 0 ? (
        <p className="py-4 text-center text-xs text-ink-muted">
          No scores on this {spanPk ? "span" : "trace"} yet
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {shown.map((score) => (
            <li key={score.id} className="rounded-lg bg-surface-2 px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="mono min-w-0 flex-1 truncate text-xs text-ink">{score.name}</span>
                <span
                  className={`mono text-sm tabular-nums ${scoreTone(score.value ?? score.string_value)}`}
                >
                  {formatScore(score.value ?? score.string_value)}
                </span>
                {!readOnly && (
                  <button
                    type="button"
                    aria-label={`Delete score ${score.name}`}
                    className="text-ink-muted hover:text-critical"
                    onClick={() => remove.mutate(score.id)}
                  >
                    ✕
                  </button>
                )}
              </div>
              <p className="mono mt-0.5 text-[10.5px] text-ink-muted">
                {SOURCE_LABEL[score.source]} · {formatTimeAgo(score.created_at)}
              </p>
              {score.comment && (
                <p className="mt-1 text-xs whitespace-pre-wrap text-ink-secondary">
                  {score.comment}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {!readOnly && (
        <form
          className="flex flex-col gap-2 border-t border-hairline pt-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit) create.mutate(undefined);
          }}
        >
          <p className="mono text-[11px] text-ink-muted">Annotate</p>
          <div className="flex gap-2">
            <TextInput
              aria-label="Score name"
              placeholder="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mono min-w-0 flex-1 !text-xs"
            />
            <TextInput
              aria-label="Score value"
              placeholder="0.8 · true · label"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="mono w-28 min-w-0 shrink !text-xs sm:w-36"
            />
          </div>
          <TextInput
            aria-label="Comment"
            placeholder="Comment (optional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="!text-xs"
          />
          <div className="flex flex-wrap items-center gap-2">
            <PrimaryButton type="submit" disabled={!canSubmit} className="!py-1 text-xs">
              {create.isPending ? "Saving…" : "Add score"}
            </PrimaryButton>
            <GhostButton
              type="button"
              className="!py-1 text-xs"
              disabled={name.trim() === "" || create.isPending}
              onClick={() => create.mutate(true)}
            >
              Pass
            </GhostButton>
            <GhostButton
              type="button"
              className="!py-1 text-xs"
              disabled={name.trim() === "" || create.isPending}
              onClick={() => create.mutate(false)}
            >
              Fail
            </GhostButton>
            {create.isError && (
              <span className="text-xs text-critical">{(create.error as Error).message}</span>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
