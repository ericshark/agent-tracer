import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { AgentBreakdown } from "../components/AgentBreakdown";
import {
  ActivityIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ClockIcon,
  CoinIcon,
  FilterIcon,
} from "../components/icons";
import { Layout } from "../components/Layout";
import { KpiStrip, StatTile, type StatDelta } from "../components/StatTile";
import { TraceTable } from "../components/TraceTable";
import { TracesChart } from "../components/TracesChart";
import { EmptyState, Menu, MenuItem, SearchInput, Spinner } from "../components/ui";
import { api } from "../lib/api";
import {
  formatCost,
  formatCount,
  formatDuration,
  formatPercent,
  formatTokens,
} from "../lib/format";
import { subscribeLive } from "../lib/sse";
import { windowDeltas } from "../lib/stats";

const WINDOWS = [
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
];

const STATUS_FILTERS = [
  ["", "All statuses"],
  ["ok", "OK"],
  ["error", "Errors"],
  ["running", "Running"],
] as const;

/** Relative change as a delta chip; `higherIsBetter` decides its color. */
function relativeDelta(change: number | null, higherIsBetter: boolean): StatDelta | null {
  if (change === null || Math.abs(change) < 0.001) return null;
  const up = change > 0;
  return {
    text: formatPercent(Math.abs(change)),
    direction: up ? "up" : "down",
    good: up === higherIsBetter,
  };
}

export function ProjectOverviewPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const search = params.get("q") ?? "";
  const [statusFilter, setStatusFilter] = useState("");
  const [hours, setHours] = useState(24);
  const [live, setLive] = useState(false);
  const [compareBase, setCompareBase] = useState<string | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  const setSearch = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set("q", value);
    else next.delete("q");
    setParams(next, { replace: true });
  };

  const stats = useQuery({
    queryKey: ["stats", projectId, hours],
    queryFn: () => api.projectStats(projectId!, hours),
    enabled: !!projectId,
    refetchInterval: 60_000,
    placeholderData: (previous) => previous,
  });

  const traces = useQuery({
    queryKey: ["traces", projectId, statusFilter, search],
    queryFn: () =>
      api.listTraces(projectId!, { status: statusFilter || undefined, q: search || undefined }),
    enabled: !!projectId,
    placeholderData: (previous) => previous, // no skeleton flash on refetch
  });

  // Unfiltered recent runs feed the per-agent panel.
  const recent = useQuery({
    queryKey: ["traces", projectId, "recent"],
    queryFn: () => api.listTraces(projectId!, { limit: 200 }),
    enabled: !!projectId,
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
  const deltas = useMemo(
    () => (stats.data ? windowDeltas(stats.data.buckets) : null),
    [stats.data],
  );

  if (!projectId) return null;

  const windowLabel = WINDOWS.find((w) => w.hours === hours)?.label ?? `${hours}h`;
  const statusLabel = STATUS_FILTERS.find(([value]) => value === statusFilter)?.[1] ?? "Filter";

  const actions = (
    <>
      {compareBase && (
        <span className="mono hidden items-center gap-1.5 rounded-lg border border-accent/40 bg-accent-soft px-2.5 py-1 text-[11px] text-accent sm:inline-flex">
          Pick a second trace
          <button
            type="button"
            aria-label="Cancel compare"
            className="opacity-70 hover:opacity-100"
            onClick={() => setCompareBase(null)}
          >
            ✕
          </button>
        </span>
      )}
      <span
        className={`mono inline-flex items-center gap-1.5 rounded-lg border border-hairline bg-surface-1 px-2.5 py-1 text-[11px] ${
          live ? "text-good" : "text-ink-muted"
        }`}
        title={live ? "Live updates connected" : "Live updates reconnecting"}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${live ? "live-dot bg-good" : "bg-ink-muted"}`}
        />
        {live ? "Live" : "Offline"}
      </span>
    </>
  );

  const windowMenu = (
    <Menu
      label="Time window"
      triggerClassName="mono inline-flex items-center gap-1.5 rounded-lg border border-hairline bg-surface-2 px-2.5 py-1 text-xs text-ink hover:bg-surface-3"
      trigger={
        <>
          {windowLabel}
          <ChevronDownIcon size={12} />
        </>
      }
    >
      {(close) =>
        WINDOWS.map((w) => (
          <MenuItem
            key={w.hours}
            active={w.hours === hours}
            onSelect={() => {
              setHours(w.hours);
              close();
            }}
          >
            Last {w.label}
          </MenuItem>
        ))
      }
    </Menu>
  );

  const tableHeader = (
    <div className="flex flex-wrap items-center gap-2 border-b border-hairline px-5 py-3.5">
      <h3 className="mono mr-auto text-[13px] text-ink-secondary">
        Trace Health
        {traces.data && (
          <span className="ml-2 text-ink-muted">
            · {traces.data.total} trace{traces.data.total === 1 ? "" : "s"}
          </span>
        )}
      </h3>
      <SearchInput
        placeholder="Search name or trace id…"
        aria-label="Search traces"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full sm:w-60"
      />
      <Menu
        label="Filter by status"
        triggerClassName={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors hover:bg-surface-3 ${
          statusFilter
            ? "border-accent/50 bg-accent-soft text-accent"
            : "border-hairline bg-surface-2 text-ink"
        }`}
        trigger={
          <>
            <FilterIcon size={13} />
            {statusFilter ? statusLabel : "Filter"}
          </>
        }
      >
        {(close) =>
          STATUS_FILTERS.map(([value, label]) => (
            <MenuItem
              key={value}
              active={statusFilter === value}
              onSelect={() => {
                setStatusFilter(value);
                close();
              }}
            >
              {label}
            </MenuItem>
          ))
        }
      </Menu>
    </div>
  );

  return (
    <Layout title="Overview" actions={actions}>
      <div className="flex flex-col gap-5">
        {stats.data ? (
          <KpiStrip>
            <StatTile
              icon={<CheckCircleIcon size={14} />}
              label="Success Rate"
              value={formatPercent(1 - stats.data.error_rate)}
              sub={`${formatCount(stats.data.error_count)} failed`}
              delta={
                deltas?.successPts != null && Math.abs(deltas.successPts) >= 0.1
                  ? {
                      text: `${Math.abs(deltas.successPts).toFixed(1)}pt`,
                      direction: deltas.successPts > 0 ? "up" : "down",
                      good: deltas.successPts > 0,
                    }
                  : null
              }
            />
            <StatTile
              icon={<ActivityIcon size={14} />}
              label={`Traces (${windowLabel})`}
              value={formatCount(stats.data.trace_count)}
              sub={`in the last ${windowLabel}`}
              delta={relativeDelta(deltas?.traces ?? null, true)}
            />
            <StatTile
              icon={<ClockIcon size={14} />}
              label="P95 Latency"
              value={formatDuration(stats.data.p95_duration_ms)}
              sub={`avg ${formatDuration(stats.data.avg_duration_ms)}`}
              delta={relativeDelta(deltas?.latency ?? null, false)}
            />
            <StatTile
              icon={<CoinIcon size={14} />}
              label="LLM Spend"
              value={formatCost(stats.data.total_cost_usd)}
              sub={`${formatTokens(
                stats.data.total_input_tokens + stats.data.total_output_tokens,
              )} tokens`}
              delta={relativeDelta(deltas?.cost ?? null, false)}
            />
          </KpiStrip>
        ) : stats.isLoading ? (
          <Spinner label="Loading stats…" />
        ) : null}

        {stats.data && (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
            <TracesChart buckets={stats.data.buckets} controls={windowMenu} />
            <AgentBreakdown
              traces={recent.data?.items ?? []}
              onViewAll={() => tableRef.current?.scrollIntoView({ behavior: "smooth" })}
            />
          </div>
        )}

        <div ref={tableRef} className="scroll-mt-20">
          {traces.isLoading ? (
            <Spinner label="Loading traces…" />
          ) : items.length === 0 && !hasAny ? (
            <OnboardingEmptyState projectId={projectId} />
          ) : (
            <div style={{ opacity: traces.isFetching && !traces.isLoading ? 0.75 : 1 }}>
              <TraceTable
                traces={items}
                projectId={projectId}
                compareBase={compareBase}
                onPickCompare={pickCompare}
                header={tableHeader}
              />
              {items.length === 0 && (
                <p className="mono mt-3 text-center text-xs text-ink-muted">
                  No traces match the current filters
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}

function OnboardingEmptyState({ projectId }: { projectId: string }) {
  return (
    <EmptyState title="No traces yet — instrument your app to see them here">
      <div className="mt-2 text-left">
        <p className="mb-2">Create an API key in Settings, then send your first trace:</p>
        <pre className="mono overflow-x-auto rounded-lg border border-hairline bg-surface-2 p-3 text-left text-[11px] leading-relaxed text-ink-secondary">
          {`pip install agent-tracer-sdk

from agent_tracer import AgentTracer
tracer = AgentTracer(api_key="at_…")

with tracer.trace("my-agent"):
    with tracer.llm(model="claude-opus-5", messages=msgs) as llm:
        llm.set_output(reply)`}
        </pre>
        <Link
          to={`/projects/${projectId}/settings`}
          className="mt-3 inline-flex rounded-lg border border-hairline bg-surface-2 px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface-3"
        >
          Open Settings →
        </Link>
      </div>
    </EmptyState>
  );
}
