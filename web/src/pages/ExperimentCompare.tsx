import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { scoreDisplay } from "../components/ExperimentBits";
import { ArrowDownIcon, ArrowUpIcon } from "../components/icons";
import { Layout } from "../components/Layout";
import { EmptyState, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { formatScore } from "../lib/format";
import { preview } from "../lib/json";
import type { CompareScoreEntry } from "../lib/types";

/** Change vs. the baseline. Direction is shown by arrow and sign, not color alone. */
function Delta({ entry }: { entry: CompareScoreEntry }) {
  if (entry.delta === undefined) return <span className="text-ink-muted">baseline</span>;
  if (entry.delta === null) return <span className="text-ink-muted">no paired cases</span>;
  const flat = Math.abs(entry.delta) < 1e-9;
  const up = entry.delta > 0;
  // An interval that excludes zero is the signal worth acting on.
  const decisive =
    entry.ci_low != null && entry.ci_high != null && (entry.ci_low > 0 || entry.ci_high < 0);
  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-x-2">
      <span
        className={`inline-flex items-center gap-0.5 tabular-nums ${
          flat ? "text-ink-muted" : up ? "text-good" : "text-critical"
        }`}
      >
        {!flat && (up ? <ArrowUpIcon size={12} /> : <ArrowDownIcon size={12} />)}
        {up ? "+" : ""}
        {entry.delta.toFixed(3)}
      </span>
      <span className="text-[10.5px] text-ink-muted tabular-nums">
        {entry.improved}↑ {entry.regressed}↓ {entry.unchanged}=
        {entry.ci_low != null && ` · 95% CI ${entry.ci_low} to ${entry.ci_high}`}
        {decisive ? "" : entry.ci_low != null ? " (inconclusive)" : ""}
      </span>
    </span>
  );
}

export function ExperimentComparePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [params] = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter(Boolean);

  const comparison = useQuery({
    queryKey: ["experiment-compare", ids.join(",")],
    queryFn: () => api.compareExperiments(ids),
    enabled: ids.length >= 2,
  });

  if (ids.length < 2) {
    return (
      <Layout title="Compare experiments">
        <EmptyState title="Select at least two experiments to compare" />
      </Layout>
    );
  }
  if (comparison.isLoading || !comparison.data) {
    return (
      <Layout title="Compare experiments">
        {comparison.isError ? (
          <EmptyState title={(comparison.error as Error).message} />
        ) : (
          <Spinner label="Comparing…" />
        )}
      </Layout>
    );
  }

  const { experiments, scores, rows } = comparison.data;
  const scoreNames = Object.keys(scores);

  return (
    <Layout title="Compare experiments">
      <nav className="mono mb-3 text-[11px] text-ink-muted">
        <Link to={`/projects/${projectId}/experiments`} className="hover:text-ink-secondary">
          Experiments
        </Link>
        <span className="mx-1.5">/</span>
        <span>Compare</span>
      </nav>

      <div className="card mb-5">
        <div className="overflow-x-auto rounded-[12px]">
          <table className="mono w-full min-w-[640px] text-[13px]">
            <thead>
              <tr className="border-b border-hairline text-left text-xs text-ink-secondary">
                <th className="px-5 py-2.5 font-medium">Score</th>
                {experiments.map((experiment, index) => (
                  <th key={experiment.id} className="px-3 py-2.5 text-right font-medium">
                    <Link
                      to={`/projects/${projectId}/experiments/${experiment.id}`}
                      className="hover:text-accent"
                    >
                      {experiment.name}
                    </Link>
                    {index === 0 && <span className="ml-1 text-ink-muted">(baseline)</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scoreNames.length === 0 && (
                <tr>
                  <td colSpan={experiments.length + 1} className="px-5 py-4 text-xs text-ink-muted">
                    These experiments have no scores to compare.
                  </td>
                </tr>
              )}
              {scoreNames.map((name) => (
                <tr key={name} className="border-b border-hairline align-top last:border-0">
                  <td className="px-5 py-2.5 text-ink">{name}</td>
                  {scores[name].map((entry) => (
                    <td key={entry.experiment_id} className="px-3 py-2.5 text-right">
                      <span className="block text-ink tabular-nums">{formatScore(entry.mean)}</span>
                      <span className="block text-[11px]">
                        <Delta entry={entry} />
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="overflow-x-auto rounded-[12px]">
          <table className="mono w-full min-w-[900px] text-[12px]">
            <thead>
              <tr className="border-b border-hairline text-left text-xs text-ink-secondary">
                <th className="px-5 py-2.5 font-medium">Input</th>
                <th className="px-3 py-2.5 font-medium">Expected</th>
                {experiments.map((experiment) => (
                  <th key={experiment.id} className="px-3 py-2.5 font-medium">
                    {experiment.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-b border-hairline align-top last:border-0">
                  <td className="max-w-[220px] px-5 py-2.5 break-words text-ink-secondary">
                    {preview(row.input, 100)}
                  </td>
                  <td className="max-w-[180px] px-3 py-2.5 break-words text-ink-muted">
                    {preview(row.expected_output, 80)}
                  </td>
                  {experiments.map((experiment) => {
                    const cell = row.cells[experiment.id];
                    if (!cell) {
                      return (
                        <td key={experiment.id} className="px-3 py-2.5 text-ink-muted">
                          not run
                        </td>
                      );
                    }
                    const output =
                      typeof cell.output === "object" && cell.output && "content" in cell.output
                        ? (cell.output as { content: unknown }).content
                        : cell.output;
                    return (
                      <td key={experiment.id} className="max-w-[260px] px-3 py-2.5 break-words">
                        <span className={cell.status === "error" ? "text-critical" : "text-ink-secondary"}>
                          {cell.status === "error" ? (cell.error ?? "error") : preview(output, 110)}
                        </span>
                        <span className="mt-1 flex flex-wrap gap-x-3 text-[10.5px]">
                          {scoreNames.map((name) => {
                            const shown = scoreDisplay(cell.scores[name]);
                            return (
                              <span key={name} title={shown.title}>
                                <span className="text-ink-muted">{name}</span>{" "}
                                <span className={`tabular-nums ${shown.tone}`}>{shown.text}</span>
                              </span>
                            );
                          })}
                          {cell.trace_pk && (
                            <Link
                              to={`/projects/${projectId}/traces/${cell.trace_pk}`}
                              className="text-ink-muted hover:text-accent"
                            >
                              trace →
                            </Link>
                          )}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
