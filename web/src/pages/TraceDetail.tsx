import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ShareIcon } from "../components/icons";
import { Layout } from "../components/Layout";
import { ShareModal } from "../components/ShareModal";
import { MetricRow } from "../components/StatTile";
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
      <Layout title="Trace">
        <Spinner label="Loading trace…" />
      </Layout>
    );
  }

  const data = trace.data;

  return (
    <Layout
      title="Trace"
      actions={
        <GhostButton onClick={() => setSharing(true)} className="!py-1 text-xs">
          <ShareIcon size={13} />
          Share
        </GhostButton>
      }
    >
      <nav className="mono mb-3 text-[11px] text-ink-muted">
        <Link to={`/projects/${projectId}`} className="hover:text-ink-secondary">
          Overview
        </Link>
        <span className="mx-1.5">/</span>
        <span>{data.trace_id.slice(0, 16)}…</span>
      </nav>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="mono text-xl text-ink">{data.name}</h2>
        <StatusBadge status={data.status} />
      </div>

      <div className="mb-5">
        <MetricRow
          items={[
            { label: "Duration", value: formatDuration(data.duration_ms) },
            { label: "Spans", value: data.span_count },
            { label: "LLM calls", value: data.llm_call_count },
            {
              label: "Tokens in / out",
              value: `${formatTokens(data.input_tokens)} / ${formatTokens(data.output_tokens)}`,
            },
            { label: "Cost", value: formatCost(data.cost_usd) },
            { label: "Session", value: data.session_id ?? "—" },
          ]}
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Waterfall
          spans={spans}
          selectedId={selectedSpanId}
          onSelect={(span) => setSelectedSpanId(span.id)}
        />
        <div className="min-h-[420px] xl:sticky xl:top-[72px] xl:max-h-[calc(100vh-6rem)]">
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
