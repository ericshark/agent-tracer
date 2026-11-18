import { useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { MetricRow } from "../components/StatTile";
import { EmptyState, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { formatDuration, formatTokens } from "../lib/format";
import type { PublicTrace } from "../lib/types";

export function SharedMetrics({ trace }: { trace: PublicTrace }) {
  return <MetricRow items={[
    { label: "Duration", value: formatDuration(trace.duration_ms) },
    { label: "Spans", value: trace.span_count },
    { label: "Errors", value: trace.error_count },
    { label: "LLM calls", value: trace.llm_call_count },
    { label: "Tokens", value: formatTokens(trace.input_tokens + trace.output_tokens) },
  ]} />;
}

export function SharePage() {
  const { token: legacyToken } = useParams<{ token: string }>();
  const token = useLocation().hash.slice(1) || legacyToken;
  const shared = useQuery({
    queryKey: ["shared", token],
    queryFn: () => api.getSharedTrace(token!),
    enabled: !!token,
    retry: false,
    gcTime: 0,
  });

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="mb-3 text-xl text-ink">Shared trace</h1>
      <p className="mb-5 text-sm text-ink-muted">Aggregate metrics only.</p>
      {shared.isLoading ? <Spinner label="Loading shared trace…" />
        : shared.error || !shared.data
          ? <EmptyState title="This share link is invalid, expired, or was revoked" />
          : <SharedMetrics trace={shared.data} />}
    </main>
  );
}
