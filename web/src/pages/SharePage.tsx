import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { LogoMark } from "../components/icons";
import { SpanInspector } from "../components/SpanInspector";
import { MetricRow } from "../components/StatTile";
import { Waterfall } from "../components/Waterfall";
import { EmptyState, Spinner, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatCost, formatDuration, formatTokens } from "../lib/format";
import { pickDefaultSpan } from "../lib/spanTree";
import type { Span } from "../lib/types";

/** Public read-only trace view for share links. No auth, no navigation. */
export function SharePage() {
  const { token } = useParams<{ token: string }>();
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);

  const shared = useQuery({
    queryKey: ["shared", token],
    queryFn: () => api.getSharedTrace(token!),
    enabled: !!token,
    retry: false,
  });

  const spans = useMemo(() => shared.data?.spans ?? [], [shared.data?.spans]);
  useEffect(() => {
    if (!spans.length || selectedSpanId) return;
    setSelectedSpanId(pickDefaultSpan(spans)?.id ?? null);
  }, [spans, selectedSpanId]);

  const selectedSpan: Span | null = spans.find((s) => s.id === selectedSpanId) ?? null;

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-hairline bg-page/85 backdrop-blur">
        <div className="flex h-14 items-center gap-3 px-4 md:px-6">
          <span className="flex items-center gap-2.5 text-ink">
            <LogoMark size={22} className="text-ink-secondary" />
            <span className="mono text-sm font-medium tracking-tight">agent-tracer</span>
          </span>
          <span className="h-5 w-px bg-hairline" aria-hidden />
          <h1 className="title-bracket text-[15px] text-ink">Shared Trace</h1>
          <span className="mono ml-auto rounded-lg border border-hairline bg-surface-1 px-2.5 py-1 text-[11px] text-ink-muted">
            Read-only
          </span>
        </div>
      </header>

      <main className="px-4 py-5 md:px-6">
        {shared.isLoading ? (
          <Spinner label="Loading shared trace…" />
        ) : shared.error || !shared.data ? (
          <EmptyState title="This share link is invalid, expired, or was revoked" />
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <h2 className="mono text-xl text-ink">{shared.data.trace.name}</h2>
              <StatusBadge status={shared.data.trace.status} />
            </div>

            <div className="mb-5">
              <MetricRow
                items={[
                  { label: "Project", value: shared.data.project_name },
                  { label: "Duration", value: formatDuration(shared.data.trace.duration_ms) },
                  { label: "Spans", value: shared.data.trace.span_count },
                  { label: "LLM calls", value: shared.data.trace.llm_call_count },
                  {
                    label: "Tokens",
                    value: formatTokens(
                      shared.data.trace.input_tokens + shared.data.trace.output_tokens,
                    ),
                  },
                  { label: "Cost", value: formatCost(shared.data.trace.cost_usd) },
                ]}
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
              <Waterfall
                spans={spans}
                selectedId={selectedSpanId}
                onSelect={(span) => setSelectedSpanId(span.id)}
              />
              <div className="min-h-[420px]">
                {selectedSpan && <SpanInspector span={selectedSpan} readOnly />}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
