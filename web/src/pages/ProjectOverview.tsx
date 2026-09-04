import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Layout } from "../components/Layout";
import { StatTile } from "../components/StatTile";
import { TraceTable } from "../components/TraceTable";
import { TracesChart } from "../components/TracesChart";
import { EmptyState, GhostButton, Spinner, TextInput } from "../components/ui";
import { api } from "../lib/api";
import {
  formatCost,
  formatCount,
  formatDuration,
  formatPercent,
  formatTokens,
} from "../lib/format";
import { subscribeLive } from "../lib/sse";

export function ProjectOverviewPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [live, setLive] = useState(false);
  const [compareBase, setCompareBase] = useState<string | null>(null);

  const stats = useQuery({
    queryKey: ["stats", projectId],
    queryFn: () => api.projectStats(projectId!),
    enabled: !!projectId,
    refetchInterval: 60_000,
  });

  const traces = useQuery({
    queryKey: ["traces", projectId, statusFilter, search],
    queryFn: () =>
      api.listTraces(projectId!, { status: statusFilter || undefined, q: search || undefined }),
    enabled: !!projectId,
    placeholderData: (previous) => previous, // no skeleton flash on refetch
  });

  // Live updates: refresh the list (debounced by react-query) on any event.
  useEffect(() => {
    if (!projectId) return;
    const unsubscribe = subscribeLive(
      projectId,
      (event) => {
        if (event.type === "trace.updated") {
          void queryClient.invalidateQueries({ queryKey: ["traces", projectId] });
          void queryClient.invalidateQueries({ queryKey: ["stats", projectId] });
        }
      },
      { onStatus: setLive },
    );
    return unsubscribe;
  }, [projectId, queryClient]);

  const pickCompare = (tracePk: string) => {
    if (compareBase === null) {
      setCompareBase(tracePk);
    } else if (compareBase === tracePk) {
      setCompareBase(null);
    } else {
      navigate(`/projects/${projectId}/compare?base=${compareBase}&other=${tracePk}`);
    }
  };

  const items = traces.data?.items ?? [];
  const hasAny = useMemo(
    () => items.length > 0 || statusFilter !== "" || search !== "",
    [items.length, statusFilter, search],
  );

  if (!projectId) return null;

  return (
    <Layout>
      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-lg font-semibold">Traces</h1>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-2 py-0.5 text-[11px] ${
            live ? "text-good" : "text-ink-muted"
          }`}
          title={live ? "Live updates connected" : "Live updates reconnecting"}
        >
          <span className={live ? "live-dot" : ""}>●</span>
          {live ? "Live" : "Offline"}
        </span>
        {compareBase && (
          <span className="rounded-full border border-accent/50 bg-accent-soft px-2.5 py-0.5 text-[11px] text-accent">
            Comparing — pick a second trace
            <button
              type="button"
              className="ml-2 opacity-70 hover:opacity-100"
              onClick={() => setCompareBase(null)}
            >
              ✕
            </button>
          </span>
        )}
      </div>

      {stats.data && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              label="Traces (24h)"
              value={formatCount(stats.data.trace_count)}
              sub={`${stats.data.error_count} with errors`}
            />
            <StatTile
              label="Error rate"
              value={formatPercent(stats.data.error_rate)}
              sub="of traces in window"
            />
            <StatTile
              label="P95 duration"
              value={formatDuration(stats.data.p95_duration_ms)}
              sub={`avg ${formatDuration(stats.data.avg_duration_ms)}`}
            />
            <StatTile
              label="LLM spend (24h)"
              value={formatCost(stats.data.total_cost_usd)}
              sub={`${formatTokens(
                stats.data.total_input_tokens + stats.data.total_output_tokens,
              )} tokens`}
            />
          </div>
          <div className="mb-4">
            <TracesChart buckets={stats.data.buckets} />
          </div>
        </>
      )}

      {/* one filter row scoping the table below */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <TextInput
          placeholder="Search by name or trace id…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
        <div className="flex items-center gap-1" role="group" aria-label="Filter by status">
          {[
            ["", "All"],
            ["ok", "OK"],
            ["error", "Errors"],
            ["running", "Running"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setStatusFilter(value)}
              className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                statusFilter === value
                  ? "bg-accent-soft font-medium text-accent"
                  : "text-ink-muted hover:bg-surface-2"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {traces.data && (
          <span className="ml-auto text-xs text-ink-muted">
            {traces.data.total} trace{traces.data.total === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {traces.isLoading ? (
        <Spinner label="Loading traces…" />
      ) : items.length === 0 && !hasAny ? (
        <OnboardingEmptyState projectId={projectId} />
      ) : items.length === 0 ? (
        <EmptyState title="No traces match the current filters" />
      ) : (
        <div style={{ opacity: traces.isFetching && !traces.isLoading ? 0.75 : 1 }}>
          <TraceTable
            traces={items}
            projectId={projectId}
            compareBase={compareBase}
            onPickCompare={pickCompare}
          />
        </div>
      )}
    </Layout>
  );
}

function OnboardingEmptyState({ projectId }: { projectId: string }) {
  return (
    <EmptyState title="No traces yet — instrument your app to see them here">
      <div className="mt-2 text-left">
        <p className="mb-2">
          Create an API key in Settings, then send your first trace:
        </p>
        <pre className="mono overflow-x-auto rounded-md bg-surface-2 p-3 text-left text-[11px] leading-relaxed">
          {`pip install agent-tracer-sdk

from agent_tracer import AgentTracer
tracer = AgentTracer(api_key="at_…")

with tracer.trace("my-agent"):
    with tracer.llm(model="claude-opus-5", messages=msgs) as llm:
        llm.set_output(reply)`}
        </pre>
        <GhostButton
          className="mt-3"
          onClick={() => (window.location.href = `/projects/${projectId}/settings`)}
        >
          Open Settings →
        </GhostButton>
      </div>
    </EmptyState>
  );
}
