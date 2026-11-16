import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { AgentBreakdown } from "../components/AgentBreakdown";
import {
  ActivityIcon,
  BotIcon,
  ClockIcon,
  CoinIcon,
  CompareIcon,
  KeyIcon,
  LogoMark,
  MoonIcon,
  ReplayIcon,
  ShareIcon,
  SunIcon,
  TraceIcon,
  CheckCircleIcon,
  CodeIcon,
} from "../components/icons";
import { SpanInspector } from "../components/SpanInspector";
import { KpiStrip, StatTile } from "../components/StatTile";
import { TracesChart } from "../components/TracesChart";
import { CopyButton, IconChip, LinkButton } from "../components/ui";
import { Waterfall } from "../components/Waterfall";
import {
  LANDING_BUCKETS,
  LANDING_SPANS,
  LANDING_TRACES,
  SDK_SNIPPET,
} from "../lib/landingData";
import { formatCost, formatCount, formatDuration, formatPercent } from "../lib/format";
import { percentile, windowDeltas } from "../lib/stats";
import { useTheme } from "../lib/theme";
import { useAuth } from "../state/auth";

const FEATURES: Array<{ icon: ReactNode; title: string; body: string }> = [
  {
    icon: <ActivityIcon size={16} />,
    title: "Live traces",
    body: "Runs stream into your dashboard as they happen over SSE, with volume, error rate, latency and spend at a glance.",
  },
  {
    icon: <TraceIcon size={16} />,
    title: "Waterfall timeline",
    body: "Every agent, model call, tool and retrieval step on one timeline, color-coded by kind, with the failing step opened first.",
  },
  {
    icon: <BotIcon size={16} />,
    title: "Span inspector",
    body: "Inspect inputs, outputs, attributes and stack traces. LLM spans render as chat messages with model, tokens and cost.",
  },
  {
    icon: <ReplayIcon size={16} />,
    title: "Model-call replay",
    body: "Re-run a single model call with the recorded or edited input. Tools never run and the original trace is never touched.",
  },
  {
    icon: <CompareIcon size={16} />,
    title: "Run comparison",
    body: "Line up two runs step by step: status flips, missing steps, and latency, token and cost deltas.",
  },
  {
    icon: <ShareIcon size={16} />,
    title: "Read-only share links",
    body: "Send a teammate a revocable, optionally expiring link. No account needed to view it.",
  },
  {
    icon: <CoinIcon size={16} />,
    title: "Cost & token tracking",
    body: "Token counts are priced from a built-in model table, or override the cost yourself per span.",
  },
  {
    icon: <CodeIcon size={16} />,
    title: "SDK + OpenTelemetry",
    body: "A tiny Python SDK, or point any OpenInference / OTLP exporter at the ingest endpoint.",
  },
  {
    icon: <KeyIcon size={16} />,
    title: "Projects & API keys",
    body: "Organize traces by project. API keys are hashed at rest and shown once; replay credentials are encrypted.",
  },
];

const STEPS = [
  { n: "01", title: "Instrument", body: "Install the SDK and wrap your agent, model and tool calls." },
  { n: "02", title: "Run", body: "Spans are batched in the background and streamed to Agent Tracer." },
  { n: "03", title: "Inspect", body: "Open the waterfall, replay a bad call, compare against a good run." },
];

export function LandingPage() {
  const { user } = useAuth();
  const [theme, toggleTheme] = useTheme();
  const [selectedId, setSelectedId] = useState<string>("s6");
  const selected = LANDING_SPANS.find((s) => s.id === selectedId) ?? LANDING_SPANS[0];

  const stats = useMemo(() => {
    const total = LANDING_BUCKETS.reduce((n, b) => n + b.trace_count, 0);
    const errors = LANDING_BUCKETS.reduce((n, b) => n + b.error_count, 0);
    const cost = LANDING_BUCKETS.reduce((n, b) => n + b.cost_usd, 0);
    const p95 = percentile(
      LANDING_TRACES.map((t) => t.duration_ms).filter((d): d is number => d !== null),
      95,
    );
    return { total, errors, cost, p95, deltas: windowDeltas(LANDING_BUCKETS) };
  }, []);

  const showDemo = !import.meta.env.VITE_API_BASE_URL;

  return (
    <div className="min-h-full bg-page text-ink">
      {/* ------------------------------------------------------------- nav */}
      <header className="sticky top-0 z-30 border-b border-hairline bg-page/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <LogoMark size={22} className="text-accent" />
            <span className="mono text-[15px] font-medium tracking-tight">agent-tracer</span>
          </Link>
          <nav className="mono ml-6 hidden items-center gap-5 text-[13px] text-ink-secondary md:flex">
            <a href="#preview" className="hover:text-ink">Preview</a>
            <a href="#features" className="hover:text-ink">Features</a>
            <a href="#sdk" className="hover:text-ink">SDK</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              className="grid h-8 w-8 place-items-center rounded-lg text-ink-secondary hover:bg-surface-2 hover:text-ink"
            >
              {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
            </button>
            {user ? (
              <LinkButton to="/projects">Open dashboard</LinkButton>
            ) : (
              <>
                <LinkButton to="/login" variant="ghost">Sign in</LinkButton>
                <LinkButton to="/login?mode=register" className="hidden sm:inline-flex">
                  Get started
                </LinkButton>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        {/* ------------------------------------------------------------ hero */}
        <section className="dot-grid border-b border-hairline">
          <div className="mx-auto max-w-4xl px-4 pt-16 pb-12 text-center sm:px-6 sm:pt-24">
            <p className="mono mb-5 inline-flex items-center gap-2 rounded-full border border-hairline bg-surface-1 px-3 py-1 text-[12px] text-ink-secondary">
              <span className="live-dot" aria-hidden /> Open-source agent observability
            </p>
            <h1 className="text-4xl leading-[1.08] font-semibold tracking-tight sm:text-6xl">
              See exactly what your <span className="text-accent">agents</span> did.
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-base text-ink-secondary sm:text-lg">
              Agent Tracer records every model call, tool call, token and error in your agent runs.
              Inspect them on a live timeline, replay a single call, and compare runs side by side.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              {user ? (
                <LinkButton to="/projects" className="!px-5 !py-2.5 !text-[15px]">
                  Open dashboard
                </LinkButton>
              ) : (
                <>
                  <LinkButton to="/login?mode=register" className="!px-5 !py-2.5 !text-[15px]">
                    Get started free
                  </LinkButton>
                  <LinkButton to="/login" variant="ghost" className="!px-5 !py-2.5 !text-[15px]">
                    Sign in
                  </LinkButton>
                </>
              )}
            </div>
            {showDemo && !user && (
              <p className="mono mt-4 text-[11px] text-ink-muted">
                Seeded demo: demo@agenttracer.dev / demo-password
              </p>
            )}
          </div>
        </section>

        {/* --------------------------------------------------- dashboard preview */}
        <section id="preview" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6">
          <SectionHeading
            eyebrow="Dashboard"
            title="Your whole fleet, at a glance"
            body="Volume, failures, latency and spend for every project, with per-agent health underneath."
          />
          <div className="mt-8 flex flex-col gap-4">
            <KpiStrip>
              <StatTile
                label="Traces"
                value={formatCount(stats.total)}
                sub="last 24 hours"
                icon={<TraceIcon size={14} />}
                delta={
                  stats.deltas.traces !== null
                    ? {
                        text: formatPercent(Math.abs(stats.deltas.traces)),
                        direction: stats.deltas.traces >= 0 ? "up" : "down",
                        good: stats.deltas.traces >= 0,
                      }
                    : null
                }
              />
              <StatTile
                label="Error rate"
                value={formatPercent(stats.errors / stats.total)}
                sub={`${stats.errors} failed runs`}
                icon={<CheckCircleIcon size={14} />}
              />
              <StatTile
                label="p95 latency"
                value={formatDuration(stats.p95)}
                sub="end to end"
                icon={<ClockIcon size={14} />}
              />
              <StatTile
                label="Spend"
                value={formatCost(stats.cost)}
                sub="all models"
                icon={<CoinIcon size={14} />}
              />
            </KpiStrip>
            <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <TracesChart buckets={LANDING_BUCKETS} />
              <AgentBreakdown traces={LANDING_TRACES} />
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------ trace preview */}
        <section className="border-y border-hairline bg-surface-1/40">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <SectionHeading
              eyebrow="Trace detail"
              title="Find the step that broke"
              body="Every span on one timeline. Click a step to see its input, output and, if it failed, the stack trace. This is a live sample, try it."
            />
            <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <Waterfall
                spans={LANDING_SPANS}
                selectedId={selectedId}
                onSelect={(s) => setSelectedId(s.id)}
              />
              <SpanInspector span={selected} readOnly />
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------ features */}
        <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6">
          <SectionHeading
            eyebrow="Capabilities"
            title="Everything you need to debug an agent"
            body="From the first span to a shareable post-mortem."
          />
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="card p-5">
                <IconChip>{f.icon}</IconChip>
                <h3 className="mt-4 text-[15px] font-medium">{f.title}</h3>
                <p className="mt-1.5 text-sm text-ink-secondary">{f.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ----------------------------------------------------------------- sdk */}
        <section id="sdk" className="border-y border-hairline bg-surface-1/40 scroll-mt-14">
          <div className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] gap-10 px-4 py-16 sm:px-6 lg:grid-cols-2">
            <div>
              <SectionHeading
                align="left"
                eyebrow="Get started"
                title="Three steps to your first trace"
                body="Python 3.9+, one dependency, and a no-op when no API key is set. Already on OpenTelemetry? Point your OTLP exporter at the ingest endpoint instead."
              />
              <ol className="mt-8 flex flex-col gap-5">
                {STEPS.map((s) => (
                  <li key={s.n} className="flex gap-4">
                    <span className="mono text-sm text-accent">{s.n}</span>
                    <div>
                      <h3 className="text-[15px] font-medium">{s.title}</h3>
                      <p className="text-sm text-ink-secondary">{s.body}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
            <div className="card min-w-0 overflow-hidden">
              <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
                <span className="mono text-[12px] text-ink-muted">agent.py</span>
                <CopyButton text={SDK_SNIPPET} label="Copy" />
              </div>
              <pre className="mono overflow-x-auto p-4 text-[12.5px] leading-relaxed text-ink-secondary">
                <code>{SDK_SNIPPET}</code>
              </pre>
              <div className="border-t border-hairline px-4 py-2.5">
                <code className="mono text-[12px] text-ink-muted">pip install -e sdk</code>
              </div>
            </div>
          </div>
        </section>

        {/* --------------------------------------------------------------- trust */}
        <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <ul className="mono grid gap-3 text-[13px] text-ink-secondary sm:grid-cols-2 lg:grid-cols-4">
            {[
              "Self-host with Docker Compose",
              "Hashed API keys, encrypted replay keys",
              "Revocable read-only share links",
              "MIT licensed",
            ].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <span className="text-accent" aria-hidden>✓</span> {t}
              </li>
            ))}
          </ul>
        </section>

        {/* ----------------------------------------------------------------- cta */}
        <section className="dot-grid border-t border-hairline">
          <div className="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Stop guessing. Start tracing.
            </h2>
            <p className="mt-3 text-ink-secondary">Create an account and send your first trace in minutes.</p>
            <div className="mt-7 flex flex-wrap justify-center gap-3">
              {user ? (
                <LinkButton to="/projects" className="!px-5 !py-2.5 !text-[15px]">
                  Open dashboard
                </LinkButton>
              ) : (
                <>
                  <LinkButton to="/login?mode=register" className="!px-5 !py-2.5 !text-[15px]">
                    Get started free
                  </LinkButton>
                  <LinkButton to="/login" variant="ghost" className="!px-5 !py-2.5 !text-[15px]">
                    Sign in
                  </LinkButton>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-hairline">
        <div className="mono mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-[12px] text-ink-muted sm:px-6">
          <span className="flex items-center gap-2">
            <LogoMark size={16} className="text-accent" /> agent-tracer
          </span>
          <span>MIT License</span>
        </div>
      </footer>
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  body,
  align = "center",
}: {
  eyebrow: string;
  title: string;
  body: string;
  align?: "center" | "left";
}) {
  return (
    <div className={align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-xl"}>
      <p className="title-bracket text-[13px] text-accent">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
      <p className="mt-3 text-ink-secondary">{body}</p>
    </div>
  );
}
