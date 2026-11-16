import { useEffect, useState } from "react";

import { formatCost, formatDateTime, formatDuration, formatTokens } from "../lib/format";
import type { Span } from "../lib/types";
import { asChatInput, asChatOutput, JsonView, MessageBubble, MessageList } from "./JsonView";
import { ReplayPanel } from "./ReplayPanel";
import { KindBadge, StatusBadge } from "./ui";

type Tab = "input" | "output" | "meta" | "error" | "replay";

export function SpanInspector({
  span,
  projectId,
  readOnly,
}: {
  span: Span;
  projectId?: string;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("input");

  // Reset to a sensible tab when switching spans.
  useEffect(() => {
    setTab(span.status === "error" ? "error" : "input");
  }, [span.id, span.status]);

  const tabs: Array<{ id: Tab; label: string; show: boolean }> = [
    { id: "input", label: "Input", show: true },
    { id: "output", label: "Output", show: true },
    { id: "meta", label: "Attributes", show: true },
    { id: "error", label: "Error", show: span.status === "error" || span.error_message !== null },
    { id: "replay", label: "Replay", show: !readOnly && span.kind === "LLM" && !!projectId },
  ];

  const chatInput = asChatInput(span.input);
  const chatOutput = asChatOutput(span.output);

  return (
    <div className="card flex h-full flex-col overflow-hidden">
      <div className="border-b border-hairline px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="mono mr-1 truncate text-[14px] text-ink">{span.name}</h3>
          <KindBadge kind={span.kind} />
          <StatusBadge status={span.status} />
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-3">
          <MetaItem label="Duration" value={formatDuration(span.duration_ms)} />
          <MetaItem label="Started" value={formatDateTime(span.started_at)} />
          {span.model && <MetaItem label="Model" value={span.model} mono />}
          {span.input_tokens !== null && (
            <MetaItem
              label="Tokens"
              value={`${formatTokens(span.input_tokens)} in / ${formatTokens(span.output_tokens)} out`}
            />
          )}
          {span.cost_usd !== null && <MetaItem label="Cost" value={formatCost(span.cost_usd)} />}
          <MetaItem label="Span ID" value={span.span_id} mono />
        </dl>
      </div>

      <nav className="mono flex gap-1 overflow-x-auto border-b border-hairline px-3 pt-1" role="tablist">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-t-md px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.id
                  ? "border-accent text-ink"
                  : "border-transparent text-ink-muted hover:text-ink-secondary"
              } ${t.id === "error" ? "text-critical" : ""}`}
            >
              {t.label}
            </button>
          ))}
      </nav>

      <div className="panel-scroll flex-1 overflow-y-auto p-4">
        {tab === "input" &&
          (chatInput ? (
            <MessageList messages={chatInput.messages} system={chatInput.system} />
          ) : span.input != null ? (
            <JsonView value={span.input} maxHeight={480} />
          ) : (
            <Empty label="No input recorded" />
          ))}

        {tab === "output" &&
          (chatOutput ? (
            <MessageBubble role={chatOutput.role ?? "assistant"} content={chatOutput.content} />
          ) : span.output != null ? (
            <JsonView value={span.output} maxHeight={480} />
          ) : (
            <Empty label="No output recorded" />
          ))}

        {tab === "meta" && (
          <div className="flex flex-col gap-4">
            <section>
              <h4 className="mono mb-2 text-[11px] text-ink-muted">Attributes</h4>
              {span.attributes && Object.keys(span.attributes).length > 0 ? (
                <JsonView value={span.attributes} />
              ) : (
                <Empty label="No attributes" />
              )}
            </section>
            <section>
              <h4 className="mono mb-2 text-[11px] text-ink-muted">Events</h4>
              {span.events && span.events.length > 0 ? (
                <ol className="flex flex-col gap-1.5">
                  {span.events.map((event, i) => (
                    <li key={i} className="rounded-lg bg-surface-2 px-3 py-1.5 text-xs">
                      <span className="font-medium">{event.name}</span>
                      <span className="ml-2 text-ink-muted">
                        {formatDateTime(event.timestamp)}
                      </span>
                      {event.attributes && Object.keys(event.attributes).length > 0 && (
                        <pre className="mono mt-1 whitespace-pre-wrap text-[11px] text-ink-muted">
                          {JSON.stringify(event.attributes)}
                        </pre>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <Empty label="No events" />
              )}
            </section>
          </div>
        )}

        {tab === "error" && (
          <div className="flex flex-col gap-3">
            <div className="rounded-lg border border-critical/40 bg-critical/10 px-3 py-2">
              <p className="text-xs font-semibold text-critical">
                {span.error_type ?? "Error"}
              </p>
              <p className="mt-1 text-sm">{span.error_message ?? "Unknown error"}</p>
            </div>
            {span.error_stacktrace && (
              <pre className="mono panel-scroll max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-ink-secondary">
                {span.error_stacktrace}
              </pre>
            )}
          </div>
        )}

        {tab === "replay" && projectId && <ReplayPanel span={span} projectId={projectId} />}
      </div>
    </div>
  );
}

function MetaItem({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="mono text-[10.5px] text-ink-muted">{label}</dt>
      <dd className={`mono truncate text-ink-secondary ${mono ? "text-[11px]" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="text-xs text-ink-muted">{label}</p>;
}
