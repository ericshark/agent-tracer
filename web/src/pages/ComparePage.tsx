import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Layout } from "../components/Layout";
import { EmptyState, KindBadge, Spinner, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatCost, formatDuration, formatTokens } from "../lib/format";
import type { DiffNode, SpanBrief, TraceSummary } from "../lib/types";

export function ComparePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [params] = useSearchParams();
  const base = params.get("base");
  const other = params.get("other");

  const diff = useQuery({
    queryKey: ["compare", base, other],
    queryFn: () => api.compare(base!, other!),
    enabled: !!base && !!other,
  });

  if (!base || !other) {
    return (
      <Layout>
        <EmptyState title="Pick two traces to compare">
          Use the “Compare” buttons in the trace list to select a base and a second trace.
        </EmptyState>
      </Layout>
    );
  }

  return (
    <Layout>
      <nav className="mb-3 text-xs text-ink-muted">
        <Link to={`/projects/${projectId}`} className="hover:text-ink-secondary">
          Traces
        </Link>
        <span className="mx-1.5">/</span>
        Compare
      </nav>

      {diff.isLoading ? (
        <Spinner label="Comparing traces…" />
      ) : diff.error ? (
        <EmptyState title="Could not load the comparison" />
      ) : diff.data ? (
        <>
          <div className="mb-4 grid gap-3 md:grid-cols-2">
            <TraceCard title="Base" trace={diff.data.base} projectId={projectId!} />
            <TraceCard title="Compared to" trace={diff.data.other} projectId={projectId!} />
          </div>

          <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-secondary">
            <span>{diff.data.summary.matched} matched</span>
            <span className="text-good">+{diff.data.summary.added} added</span>
            <span className="text-critical">-{diff.data.summary.removed} removed</span>
            <span className="text-accent">{diff.data.summary.changed} changed</span>
          </div>

          <div className="card overflow-x-auto">
            <div className="min-w-[860px]">
              <div className="grid grid-cols-[minmax(240px,1fr)_repeat(2,minmax(180px,1fr))_minmax(200px,1fr)] gap-2 border-b border-hairline px-4 py-2 text-[11px] font-medium text-ink-muted">
                <span>Step</span>
                <span>Base</span>
                <span>Compared</span>
                <span>Δ change</span>
              </div>
              {diff.data.nodes.map((node, i) => (
                <DiffRow key={i} node={node} depth={0} />
              ))}
            </div>
          </div>
        </>
      ) : null}
    </Layout>
  );
}

function TraceCard({
  title,
  trace,
  projectId,
}: {
  title: string;
  trace: TraceSummary;
  projectId: string;
}) {
  return (
    <div className="card p-4">
      <p className="text-xs text-ink-muted">{title}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <Link
          to={`/projects/${projectId}/traces/${trace.id}`}
          className="font-medium hover:text-accent"
        >
          {trace.name}
        </Link>
        <StatusBadge status={trace.status} />
      </div>
      <p className="mt-1 text-xs tabular-nums text-ink-muted">
        {formatDuration(trace.duration_ms)} · {trace.span_count} spans ·{" "}
        {formatTokens(trace.input_tokens + trace.output_tokens)} tokens ·{" "}
        {formatCost(trace.cost_usd)} · {new Date(trace.started_at).toLocaleString()}
      </p>
    </div>
  );
}

function DiffRow({ node, depth }: { node: DiffNode; depth: number }) {
  const span = (node.base ?? node.other)!;
  const changeLabel =
    node.change === "added" ? (
      <span className="text-[11px] font-medium text-good">+ only in compared</span>
    ) : node.change === "removed" ? (
      <span className="text-[11px] font-medium text-critical">- only in base</span>
    ) : (
      <DeltaSummary node={node} />
    );

  return (
    <>
      <div className="grid grid-cols-[minmax(240px,1fr)_repeat(2,minmax(180px,1fr))_minmax(200px,1fr)] items-center gap-2 border-b border-hairline px-4 py-2 last:border-0 hover:bg-surface-2/50">
        <span className="flex min-w-0 items-center gap-2" style={{ paddingLeft: depth * 16 }}>
          <KindBadge kind={span.kind} />
          <span className="truncate text-[13px]">{span.name}</span>
        </span>
        <SpanCell span={node.base} />
        <SpanCell span={node.other} />
        <span>{changeLabel}</span>
      </div>
      {node.children.map((child, i) => (
        <DiffRow key={i} node={child} depth={depth + 1} />
      ))}
    </>
  );
}

function SpanCell({ span }: { span: SpanBrief | null }) {
  if (!span) return <span className="text-xs text-ink-muted">—</span>;
  return (
    <span className="flex items-center gap-2 text-xs tabular-nums text-ink-secondary">
      <StatusBadge status={span.status} compact />
      {formatDuration(span.duration_ms)}
      {span.input_tokens !== null && (
        <span className="text-ink-muted">
          {formatTokens((span.input_tokens ?? 0) + (span.output_tokens ?? 0))} tok
        </span>
      )}
      {span.error_message && (
        <span className="truncate text-critical" title={span.error_message}>
          {span.error_message}
        </span>
      )}
    </span>
  );
}

function DeltaSummary({ node }: { node: DiffNode }) {
  const delta = node.delta;
  if (!delta) return null;
  const parts: Array<{ text: string; className: string }> = [];
  if (delta.status_changed) {
    parts.push({ text: "status changed", className: "text-critical font-medium" });
  }
  if (delta.output_changed) parts.push({ text: "output differs", className: "text-accent" });
  else if (delta.input_changed) parts.push({ text: "input differs", className: "text-accent" });
  if (delta.duration_ms !== undefined && Math.abs(delta.duration_ms) >= 1) {
    const sign = delta.duration_ms > 0 ? "+" : "-";
    parts.push({
      text: `${sign}${formatDuration(Math.abs(delta.duration_ms))}`,
      className: "text-ink-muted",
    });
  }
  const tokenDelta = (delta.input_tokens ?? 0) + (delta.output_tokens ?? 0);
  if (tokenDelta !== 0) {
    parts.push({
      text: `${tokenDelta > 0 ? "+" : "-"}${formatTokens(Math.abs(tokenDelta))} tok`,
      className: "text-ink-muted",
    });
  }
  if (parts.length === 0) {
    return <span className="text-[11px] text-ink-muted">no change</span>;
  }
  return (
    <span className="flex flex-wrap gap-x-2 text-[11px] tabular-nums">
      {parts.map((part, i) => (
        <span key={i} className={part.className}>
          {part.text}
        </span>
      ))}
    </span>
  );
}
