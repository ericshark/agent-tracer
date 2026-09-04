import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Layout } from "../components/Layout";
import { ShareModal } from "../components/ShareModal";
import { SpanInspector } from "../components/SpanInspector";
import { Waterfall } from "../components/Waterfall";
import { GhostButton, Spinner, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatCost, formatDuration, formatTokens } from "../lib/format";
import { pickDefaultSpan } from "../lib/spanTree";
import { subscribeLive } from "../lib/sse";
import type { Span } from "../lib/types";

export function TraceDetailPage() {
  const { projectId, tracePk } = useParams<{ projectId: string; tracePk: string }>();
  const queryClient = useQueryClient();
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);

  const trace = useQuery({
    queryKey: ["trace", tracePk],
    queryFn: () => api.getTrace(tracePk!),
    enabled: !!tracePk,
    placeholderData: (previous) => previous,
  });

  // Follow live updates while this trace is running.
  const traceId = trace.data?.trace_id;
  const isRunning = trace.data?.status === "running";
  useEffect(() => {
    if (!projectId || !traceId || !isRunning) return;
    return subscribeLive(
      projectId,
      () => void queryClient.invalidateQueries({ queryKey: ["trace", tracePk] }),
      { traceId },
    );
  }, [projectId, traceId, isRunning, tracePk, queryClient]);

  const spans = useMemo(() => trace.data?.spans ?? [], [trace.data?.spans]);

  // Open on the innermost failure when there is one, else the root span.
  useEffect(() => {
    if (!spans.length || selectedSpanId) return;
    setSelectedSpanId(pickDefaultSpan(spans)?.id ?? null);
  }, [spans, selectedSpanId]);

  const selectedSpan: Span | null =
    spans.find((s) => s.id === selectedSpanId) ?? null;

  if (trace.isLoading || !trace.data) {
    return (
      <Layout>
        <Spinner label="Loading trace…" />
      </Layout>
    );
  }

  const data = trace.data;

  return (
    <Layout>
      <nav className="mb-3 text-xs text-ink-muted">
        <Link to={`/projects/${projectId}`} className="hover:text-ink-secondary">
          Traces
        </Link>
        <span className="mx-1.5">/</span>
        <span className="mono">{data.trace_id.slice(0, 16)}…</span>
      </nav>

      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-lg font-semibold">{data.name}</h1>
        <StatusBadge status={data.status} />
        <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
          <span className="tabular-nums">{formatDuration(data.duration_ms)}</span>
          <span>{data.span_count} spans</span>
          <span>{data.llm_call_count} LLM calls</span>
          <span className="tabular-nums">
            {formatTokens(data.input_tokens)} in / {formatTokens(data.output_tokens)} out
          </span>
          <span className="tabular-nums">{formatCost(data.cost_usd)}</span>
          {data.session_id && <span>session {data.session_id}</span>}
        </dl>
        <div className="ml-auto flex items-center gap-2">
          <GhostButton onClick={() => setSharing(true)}>Share</GhostButton>
          <Link to={`/projects/${projectId}?`} className="hidden" aria-hidden />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Waterfall
          spans={spans}
          selectedId={selectedSpanId}
          onSelect={(span) => setSelectedSpanId(span.id)}
        />
        <div className="min-h-[420px] xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)]">
          {selectedSpan ? (
            <SpanInspector span={selectedSpan} projectId={projectId} />
          ) : (
            <div className="card grid h-full place-items-center text-sm text-ink-muted">
              Select a span to inspect it
            </div>
          )}
        </div>
      </div>

      {sharing && tracePk && <ShareModal tracePk={tracePk} onClose={() => setSharing(false)} />}
    </Layout>
  );
}
