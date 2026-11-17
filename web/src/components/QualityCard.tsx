import { formatCount, formatScore } from "../lib/format";
import type { ScoreSummary } from "../lib/types";
import { scoreTone } from "./Scores";

/** Mean-over-time sparkline. Gaps (buckets with no scores) break the line. */
function Sparkline({ series }: { series: ScoreSummary["series"] }) {
  const points = series.map((p, i) => ({ i, mean: p.mean }));
  const values = points.flatMap((p) => (p.mean === null ? [] : [p.mean]));
  if (values.length < 2) return <span className="block h-6 w-24" aria-hidden />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 96;
  const height = 24;
  const x = (i: number) => (i / Math.max(1, series.length - 1)) * width;
  const y = (v: number) => height - 2 - ((v - min) / span) * (height - 4);

  let path = "";
  let pen = false;
  for (const p of points) {
    if (p.mean === null) {
      pen = false;
      continue;
    }
    path += `${pen ? "L" : "M"}${x(p.i).toFixed(1)},${y(p.mean).toFixed(1)} `;
    pen = true;
  }
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function topLabel(distribution: Record<string, number>): string | null {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  return `${entries[0][0]} ${Math.round((entries[0][1] / total) * 100)}%`;
}

export function QualityCard({ summaries }: { summaries: ScoreSummary[] }) {
  if (summaries.length === 0) return null;
  return (
    <div className="card p-5">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="mono text-[13px] text-ink-secondary">Quality</h3>
        <p className="text-[11px] text-ink-muted">mean score, last 7 days</p>
      </div>
      <ul className="grid gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
        {summaries.map((s) => {
          const headline = s.data_type === "categorical" ? topLabel(s.distribution) : s.mean;
          return (
            <li
              key={s.name}
              className="flex items-center justify-between gap-3 border-t border-hairline py-2.5"
            >
              <div className="min-w-0">
                <p className="mono truncate text-[13px] text-ink" title={s.name}>
                  {s.name}
                </p>
                <p className="mono text-[10.5px] text-ink-muted tabular-nums">
                  {formatCount(s.count)} score{s.count === 1 ? "" : "s"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {s.data_type !== "categorical" && <Sparkline series={s.series} />}
                <span
                  className={`mono w-16 text-right text-sm tabular-nums ${scoreTone(headline)}`}
                >
                  {formatScore(headline)}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
