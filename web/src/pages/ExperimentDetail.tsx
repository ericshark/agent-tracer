import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ExperimentStatus, ScoreMeter, scoreDisplay } from "../components/ExperimentBits";
import { Layout } from "../components/Layout";
import { MetricRow } from "../components/StatTile";
import { EmptyState, GhostButton, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { formatCost, formatDuration, formatTokens } from "../lib/format";
import { preview } from "../lib/json";
import { subscribeLive } from "../lib/sse";

export function ExperimentDetailPage() {
  const { projectId, experimentId } = useParams<{ projectId: string; experimentId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const experiment = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => api.getExperiment(experimentId!),
    enabled: !!experimentId,
  });
  const items = useQuery({
    queryKey: ["experiment-items", experimentId],
    queryFn: () => api.listExperimentItems(experimentId!),
    enabled: !!experimentId,
  });

  const active = experiment.data?.status === "running" || experiment.data?.status === "pending";
  useEffect(() => {
    if (!projectId || !active) return;
    return subscribeLive(projectId, (event) => {
      if (event.type === "experiment.updated" && event.experiment_id === experimentId) {
        void queryClient.invalidateQueries({ queryKey: ["experiment", experimentId] });
        void queryClient.invalidateQueries({ queryKey: ["experiment-items", experimentId] });
      }
    });
  }, [projectId, experimentId, active, queryClient]);

  const remove = useMutation({
    mutationFn: () => api.deleteExperiment(experimentId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["experiments", projectId] });
      navigate(`/projects/${projectId}/experiments`);
    },
  });

  if (experiment.isLoading || !experiment.data) {
    return (
      <Layout title="Experiment">
        {experiment.isError ? <EmptyState title="Experiment not found" /> : <Spinner />}
      </Layout>
    );
  }

  const data = experiment.data;
  const summary = data.summary;
  const rows = items.data?.items ?? [];
  const scoreNames = Array.from(
    new Set([
      ...Object.keys(summary?.scores ?? {}),
      ...rows.flatMap((row) => Object.keys(row.scores ?? {})),
    ]),
  );

  return (
    <Layout title="Experiment">
      <nav className="mono mb-3 text-[11px] text-ink-muted">
        <Link to={`/projects/${projectId}/experiments`} className="hover:text-ink-secondary">
          Experiments
        </Link>
        <span className="mx-1.5">/</span>
        <span>{data.name}</span>
      </nav>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="mono text-xl text-ink">{data.name}</h2>
        <ExperimentStatus experiment={data} />
        <GhostButton
          className="ml-auto !py-1 text-xs hover:!text-critical"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Delete experiment "${data.name}"?`)) remove.mutate();
          }}
        >
          Delete
        </GhostButton>
      </div>

      {data.error && (
        <p className="mb-4 rounded-lg border border-critical/40 bg-critical/10 px-3 py-2 text-sm">
          {data.error}
        </p>
      )}

      <div className="mb-5 flex flex-col gap-4">
        <MetricRow
          items={[
            { label: "Target", value: data.target.type === "sdk" ? "SDK run" : (data.target.model ?? "—") },
            { label: "Cases", value: `${data.completed_count} / ${data.item_count}` },
            { label: "Errors", value: summary?.error_count ?? "—" },
            { label: "Avg latency", value: formatDuration(summary?.avg_latency_ms) },
            { label: "Tokens", value: formatTokens(summary?.total_tokens) },
            { label: "Cost", value: formatCost(summary?.total_cost_usd) },
          ]}
        />
        {summary && Object.keys(summary.scores).length > 0 && (
          <div className="card grid grid-cols-2 gap-px overflow-hidden bg-hairline lg:grid-cols-4">
            {Object.entries(summary.scores).map(([name, score]) => (
              <ScoreMeter key={name} label={name} mean={score.mean} count={score.count} />
            ))}
          </div>
        )}
      </div>

      {items.isLoading ? (
        <Spinner label="Loading results…" />
      ) : rows.length === 0 ? (
        <EmptyState title="No results yet" />
      ) : (
        <div className="card">
          <div className="overflow-x-auto rounded-[12px]">
            <table className="mono w-full min-w-[900px] text-[12px]">
              <thead>
                <tr className="border-b border-hairline text-left text-xs text-ink-secondary">
                  <th className="px-5 py-2.5 font-medium">Input</th>
                  <th className="px-3 py-2.5 font-medium">Expected</th>
                  <th className="px-3 py-2.5 font-medium">Output</th>
                  {scoreNames.map((name) => (
                    <th key={name} className="px-3 py-2.5 text-right font-medium whitespace-nowrap">
                      {name}
                    </th>
                  ))}
                  <th className="px-5 py-2.5 text-right font-medium">Latency</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-hairline align-top last:border-0 hover:bg-surface-2/60">
                    <td className="max-w-[240px] px-5 py-2.5 break-words text-ink-secondary">
                      {preview(row.input, 110)}
                    </td>
                    <td className="max-w-[200px] px-3 py-2.5 break-words text-ink-muted">
                      {preview(row.expected_output, 90)}
                    </td>
                    <td className="max-w-[280px] px-3 py-2.5 break-words text-ink-secondary">
                      {row.status === "error" ? (
                        <span className="text-critical">{row.error ?? "error"}</span>
                      ) : row.status === "pending" ? (
                        <span className="text-ink-muted">running…</span>
                      ) : (
                        preview(
                          typeof row.output === "object" && row.output && "content" in row.output
                            ? (row.output as { content: unknown }).content
                            : row.output,
                          130,
                        )
                      )}
                      {row.trace_pk && (
                        <Link
                          to={`/projects/${projectId}/traces/${row.trace_pk}`}
                          className="ml-2 text-[10.5px] text-ink-muted hover:text-accent"
                        >
                          trace →
                        </Link>
                      )}
                    </td>
                    {scoreNames.map((name) => {
                      const shown = scoreDisplay(row.scores?.[name]);
                      return (
                        <td key={name} className={`px-3 py-2.5 text-right tabular-nums ${shown.tone}`} title={shown.title}>
                          {shown.text}
                        </td>
                      );
                    })}
                    <td className="px-5 py-2.5 text-right text-ink-muted tabular-nums">
                      {formatDuration(row.latency_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Layout>
  );
}
