import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { SpanInspector } from "../components/SpanInspector";
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
      <header className="border-b border-hairline bg-page/90">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
          <span className="flex items-center gap-2 font-semibold tracking-tight">
            <span
              aria-hidden
              className="grid h-6 w-6 place-items-center rounded-md bg-accent text-[13px] font-bold text-white"
            >
              ⌁
            </span>
            Agent Tracer
          </span>
          <span className="rounded-full border border-hairline px-2 py-0.5 text-[11px] text-ink-muted">
            Shared read-only view
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {shared.isLoading ? (
          <Spinner label="Loading shared trace…" />
        ) : shared.error || !shared.data ? (
          <EmptyState title="This share link is invalid, expired, or was revoked" />
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
              <h1 className="text-lg font-semibold">{shared.data.trace.name}</h1>
              <StatusBadge status={shared.data.trace.status} />
              <span className="text-xs text-ink-muted">
                from project “{shared.data.project_name}”
              </span>
              <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
                <span className="tabular-nums">
                  {formatDuration(shared.data.trace.duration_ms)}
                </span>
                <span>{shared.data.trace.span_count} spans</span>
                <span className="tabular-nums">
                  {formatTokens(
                    shared.data.trace.input_tokens + shared.data.trace.output_tokens,
                  )}{" "}
                  tokens
                </span>
                <span className="tabular-nums">{formatCost(shared.data.trace.cost_usd)}</span>
              </dl>
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
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
