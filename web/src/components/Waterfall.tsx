import { useMemo, useState } from "react";

import { formatDuration } from "../lib/format";
import { buildSpanTree, timeExtent, type SpanNode } from "../lib/spanTree";
import type { Span, SpanKind } from "../lib/types";
import { KIND_COLOR, KindBadge } from "./ui";

const ROW_HEIGHT = 30;
const BAR_HEIGHT = 8;

const LEGEND_KINDS: SpanKind[] = ["AGENT", "LLM", "TOOL", "CHAIN", "RETRIEVER", "GUARDRAIL"];

export function Waterfall({
  spans,
  selectedId,
  onSelect,
}: {
  spans: Span[];
  selectedId: string | null;
  onSelect: (span: Span) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const roots = useMemo(() => buildSpanTree(spans), [spans]);
  const extent = useMemo(() => timeExtent(spans), [spans]);
  const total = extent.end - extent.start;

  const visible = useMemo(() => {
    const out: SpanNode[] = [];
    const walk = (nodes: SpanNode[]) => {
      for (const node of nodes) {
        out.push(node);
        if (!collapsed.has(node.span.span_id)) walk(node.children);
      }
    };
    walk(roots);
    return out;
  }, [roots, collapsed]);

  const presentKinds = useMemo(() => {
    const kinds = new Set(spans.map((s) => s.kind));
    return LEGEND_KINDS.filter((k) => kinds.has(k)).concat(
      [...kinds].filter((k) => !LEGEND_KINDS.includes(k)) as SpanKind[],
    );
  }, [spans]);

  const toggle = (spanId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(spanId)) next.delete(spanId);
      else next.add(spanId);
      return next;
    });
  };

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-hairline px-4 py-2">
        <h3 className="text-sm font-medium">Execution timeline</h3>
        <div className="flex flex-wrap items-center gap-3">
          {presentKinds.map((kind) => (
            <KindBadge key={kind} kind={kind} />
          ))}
        </div>
        <span className="ml-auto text-xs tabular-nums text-ink-muted">
          {formatDuration(total)} total
        </span>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[640px]">
          {visible.map((node) => {
            const span = node.span;
            const start = new Date(span.started_at).getTime();
            const end = span.ended_at ? new Date(span.ended_at).getTime() : extent.end;
            const leftPct = ((start - extent.start) / total) * 100;
            const widthPct = Math.max(0.4, ((end - start) / total) * 100);
            const isSelected = span.id === selectedId;
            const hasChildren = node.children.length > 0;
            const isCollapsed = collapsed.has(span.span_id);
            const running = span.status === "running";

            return (
              <button
                key={span.span_id}
                type="button"
                onClick={() => onSelect(span)}
                aria-pressed={isSelected}
                className={`grid w-full grid-cols-[minmax(220px,300px)_1fr] items-center gap-2 border-b border-hairline px-2 text-left transition-colors last:border-0 ${
                  isSelected ? "bg-accent-soft" : "hover:bg-surface-2/60"
                }`}
                style={{ height: ROW_HEIGHT }}
              >
                {/* tree cell */}
                <span
                  className="flex min-w-0 items-center gap-1.5"
                  style={{ paddingLeft: node.depth * 16 }}
                >
                  {hasChildren ? (
                    <span
                      role="button"
                      tabIndex={-1}
                      aria-label={isCollapsed ? "Expand" : "Collapse"}
                      onClick={(event) => {
                        event.stopPropagation();
                        toggle(span.span_id);
                      }}
                      className="grid h-4 w-4 shrink-0 place-items-center rounded text-[9px] text-ink-muted hover:bg-surface-2"
                    >
                      {isCollapsed ? "▶" : "▼"}
                    </span>
                  ) : (
                    <span className="w-4 shrink-0" />
                  )}
                  <span
                    aria-hidden
                    className="h-2 w-2 shrink-0 rounded-[2px]"
                    style={{ background: KIND_COLOR[span.kind] ?? KIND_COLOR.UNKNOWN }}
                  />
                  <span className="truncate text-[13px]">{span.name}</span>
                  {span.status === "error" && (
                    <span className="shrink-0 text-[11px] font-semibold text-critical" title="Error">
                      ✕
                    </span>
                  )}
                  {running && (
                    <span className="live-dot shrink-0 text-[9px] text-accent" title="Running">
                      ●
                    </span>
                  )}
                </span>

                {/* timing cell */}
                <span className="relative block h-full">
                  <span
                    className={`absolute top-1/2 -translate-y-1/2 rounded-[4px] ${running ? "live-dot" : ""}`}
                    style={{
                      left: `${leftPct}%`,
                      width: `${widthPct}%`,
                      height: BAR_HEIGHT,
                      background: KIND_COLOR[span.kind] ?? KIND_COLOR.UNKNOWN,
                    }}
                  />
                  <span
                    className="absolute top-1/2 -translate-y-1/2 whitespace-nowrap text-[10px] tabular-nums text-ink-muted"
                    style={
                      leftPct + widthPct < 82
                        ? { left: `calc(${leftPct + widthPct}% + 6px)` }
                        : { right: `calc(${100 - leftPct}% + 6px)` }
                    }
                  >
                    {running ? "running" : formatDuration(span.duration_ms)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
