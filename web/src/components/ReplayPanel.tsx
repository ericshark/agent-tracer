import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { formatCost, formatDuration, formatTimeAgo, formatTokens } from "../lib/format";
import type { Replay, Span } from "../lib/types";
import { asChatInput, MessageBubble } from "./JsonView";
import { GhostButton, PrimaryButton, Spinner, TextInput } from "./ui";

export function ReplayPanel({ span, projectId }: { span: Span; projectId: string }) {
  const queryClient = useQueryClient();
  const replays = useQuery({
    queryKey: ["replays", span.id],
    queryFn: () => api.listReplays(span.id),
  });

  const chat = useMemo(() => asChatInput(span.input), [span.input]);
  const [editing, setEditing] = useState(false);
  const [provider, setProvider] = useState<string>("");
  const [model, setModel] = useState(span.model ?? "");
  const [messagesText, setMessagesText] = useState(() =>
    JSON.stringify(chat?.messages ?? [{ role: "user", content: "" }], null, 2),
  );
  const [system, setSystem] = useState(chat?.system ?? "");
  const [maxTokens, setMaxTokens] = useState("1024");
  const [jsonError, setJsonError] = useState<string | null>(null);

  const runReplay = useMutation({
    mutationFn: async () => {
      let payload: Parameters<typeof api.createReplay>[1] = {};
      if (editing) {
        let messages: Array<{ role: string; content: unknown }>;
        try {
          messages = JSON.parse(messagesText);
          if (!Array.isArray(messages)) throw new Error("messages must be a JSON array");
        } catch (error) {
          setJsonError(error instanceof Error ? error.message : "Invalid JSON");
          throw error;
        }
        payload = {
          messages,
          model: model || undefined,
          system: system || undefined,
          params: { max_tokens: Number(maxTokens) || 1024 },
        };
      }
      if (provider) payload.provider = provider;
      setJsonError(null);
      return api.createReplay(span.id, payload);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["replays", span.id] });
    },
  });

  const mutationError =
    runReplay.error instanceof ApiError ? runReplay.error.message : jsonError;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-md border border-hairline bg-surface-2/50 px-3 py-2 text-xs text-ink-muted">
        Replays re-run <em>only this model call</em> with the recorded (or edited) input — no
        tools execute, and the original trace is never modified. Without a provider key
        (
        <Link className="text-accent hover:underline" to={`/projects/${projectId}/settings`}>
          Settings → Replay credentials
        </Link>
        ) the built-in simulator responds instead.
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Provider
          <select
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
            className="rounded-md border border-hairline bg-surface-2 px-2 py-1.5 text-sm text-ink"
          >
            <option value="">Auto</option>
            <option value="simulation">Simulation (offline)</option>
            <option value="anthropic">Anthropic</option>
            <option value="openai">OpenAI-compatible</option>
          </select>
        </label>
        <GhostButton onClick={() => setEditing(!editing)}>
          {editing ? "Use recorded input" : "Edit input"}
        </GhostButton>
        <PrimaryButton onClick={() => runReplay.mutate()} disabled={runReplay.isPending}>
          {runReplay.isPending ? "Replaying…" : "▶ Replay step"}
        </PrimaryButton>
      </div>

      {editing && (
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <label className="flex flex-1 flex-col gap-1 text-xs text-ink-muted">
              Model
              <TextInput value={model} onChange={(e) => setModel(e.target.value)} />
            </label>
            <label className="flex w-28 flex-col gap-1 text-xs text-ink-muted">
              Max tokens
              <TextInput value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            System prompt
            <textarea
              value={system}
              onChange={(e) => setSystem(e.target.value)}
              rows={2}
              className="mono rounded-md border border-hairline bg-surface-2 px-3 py-2 text-xs text-ink"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-muted">
            Messages (JSON)
            <textarea
              value={messagesText}
              onChange={(e) => setMessagesText(e.target.value)}
              rows={8}
              spellCheck={false}
              className="mono rounded-md border border-hairline bg-surface-2 px-3 py-2 text-xs text-ink"
            />
          </label>
        </div>
      )}

      {mutationError && (
        <p className="rounded-md border border-critical/40 bg-critical/10 px-3 py-2 text-xs text-critical">
          {mutationError}
        </p>
      )}

      {replays.isLoading ? (
        <Spinner label="Loading replays…" />
      ) : (
        <div className="flex flex-col gap-3">
          {(replays.data ?? []).map((replay) => (
            <ReplayResult key={replay.id} replay={replay} />
          ))}
          {(replays.data ?? []).length === 0 && (
            <p className="text-xs text-ink-muted">
              No replays yet — run one to compare fresh output against the recorded step.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ReplayResult({ replay }: { replay: Replay }) {
  return (
    <div className="rounded-md border border-hairline p-3">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
        <span
          className={`font-medium ${replay.status === "ok" ? "text-good" : "text-critical"}`}
        >
          {replay.status === "ok" ? "✓ completed" : "✕ failed"}
        </span>
        <span className="mono">{replay.model}</span>
        <span>
          via {replay.provider}
          {replay.output?.simulated ? " (simulated)" : ""}
        </span>
        <span className="tabular-nums">{formatDuration(replay.latency_ms)}</span>
        {replay.input_tokens !== null && (
          <span className="tabular-nums">
            {formatTokens(replay.input_tokens)} → {formatTokens(replay.output_tokens)} tok
          </span>
        )}
        {replay.cost_usd !== null && (
          <span className="tabular-nums">{formatCost(replay.cost_usd)}</span>
        )}
        <span className="ml-auto">{formatTimeAgo(replay.created_at)}</span>
      </div>
      {replay.status === "ok" && replay.output ? (
        <MessageBubble role={replay.output.role ?? "assistant"} content={replay.output.content} />
      ) : (
        <p className="mono whitespace-pre-wrap text-xs text-critical">{replay.error_message}</p>
      )}
    </div>
  );
}
