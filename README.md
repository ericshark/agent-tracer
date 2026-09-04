# ⌁ Agent Tracer

**A developer platform for debugging and understanding AI-agent executions.**

Instrument your agent with a three-line SDK, watch runs unfold live span by span,
inspect every model and tool call (latency, tokens, cost, inputs, outputs, errors),
replay failed LLM steps safely, diff two executions to see exactly what changed, and
share any trace through a secure read-only link.

```
┌────────────────────┐   /v1/ingest (native)    ┌───────────────┐      ┌────────────┐
│ Your Python app    │ ───────────────────────► │  FastAPI API  │ ───► │ PostgreSQL │
│ + agent-tracer-sdk │   /v1/traces (OTLP JSON) │  (async)      │      └────────────┘
└────────────────────┘                          │   │ SSE live events
      any OTel/OpenInference exporter ─────────►│   ▼
                                                │  React + Vite SPA
                                                └───────────────┘
```

- **Backend** — FastAPI (async SQLAlchemy 2.0), PostgreSQL, Alembic migrations
- **Frontend** — React 18 + TypeScript + Vite + Tailwind, live updates over SSE
- **SDK** — `agent-tracer-sdk`, a dependency-light Python tracer (httpx only) with a
  background batch exporter
- **Interop** — accepts OTLP/HTTP JSON at `/v1/traces` and maps
  [OpenInference](https://github.com/Arize-ai/openinference) / `gen_ai.*` semantic
  conventions, so existing OpenTelemetry-instrumented apps can point their exporter
  at Agent Tracer without code changes

---

## Quick start (Docker — full stack in ~2 minutes)

Requires Docker with the Compose plugin.

```bash
git clone <this-repo> && cd agent-tracer

cp .env.example .env
# Edit .env and set SECRET_KEY (required):
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up --build -d          # db + api + web
docker compose run --rm seed          # demo user, project, API key, example traces
```

The seed command prints the demo login and a fresh SDK API key:

```
Sign in at the web UI with:  demo@agenttracer.dev / demo-password
New API key (for the SDK):   at_…
```

Open **http://localhost:3000**, sign in, and explore the *Travel Concierge* demo
project. The API (with interactive docs) is at **http://localhost:8000/docs**.

### See the live view in action

```bash
python3 -m venv .venv && .venv/bin/pip install -e sdk
export AGENT_TRACER_API_KEY=at_…                 # from the seed output
export AGENT_TRACER_BASE_URL=http://localhost:8000
.venv/bin/python sdk/examples/demo_agent.py --runs 2 --fail
```

Keep the Traces page open while it runs — new runs appear and complete in real
time, and the last one fails at the tool step so you can walk the debugging flow
below.

---

## The primary debugging workflow (demo script)

1. **Traces** — the project overview shows KPI tiles (volume, error rate, p95
   latency, spend), a traces-over-time chart, and the live-updating trace list.
   Click the failing `research-agent` run (✕ Error).
2. **Timeline** — the waterfall shows the span tree with per-kind colors and
   timing bars. The failed `query_metrics` tool span is marked ✕; the inspector
   opens on its **Error** tab with the exception type, message, and stack trace.
3. **Inspect the LLM call** — select the `plan` span: the **Input** tab renders
   the chat messages (system + user), **Output** the assistant reply, with model,
   token counts, and cost in the header.
4. **Replay** — on an LLM span, open **Replay** and hit *▶ Replay step*. The step
   re-runs with its recorded input — or edit the prompt first. Replays never
   execute tools and never modify the original trace. With no provider key the
   offline simulator answers; add an Anthropic/OpenAI key under *Settings →
   Replay credentials* to replay against the real model.
5. **Compare** — back on the trace list, press *Compare* on the failed run, then
   on a successful one. The diff aligns both span trees and shows what changed:
   status flips, missing steps, output/input drift, latency/token/cost deltas.
6. **Share** — from a trace, *Share → Create link* mints a revocable, optionally
   expiring read-only URL (`/share/<256-bit-token>`) that renders the full trace
   without an account.

---

## Local development (without Docker)

Prerequisites: Python 3.11+, Node 20+, PostgreSQL 14+ (or use SQLite for a quick
hack session).

### 1. Install dependencies

```bash
make install
# or manually:
python3 -m venv .venv
.venv/bin/pip install -e "server[dev]" -e "sdk[dev]"
cd web && npm install
```

### 2. Configure environment

The API reads configuration from environment variables (or `server/.env`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://tracer:tracer@localhost:5432/agent_tracer` | Async SQLAlchemy URL (`sqlite+aiosqlite:///dev.db` also works) |
| `SECRET_KEY` | dev-only value | Signs JWTs and encrypts stored provider keys — **required in production** |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated SPA origins (dev server) |
| `ENVIRONMENT` | `development` | `production` refuses to boot with the default secret |
| `LOG_LEVEL` | `INFO` | Backend log verbosity |

```bash
createdb agent_tracer   # or: psql -c "CREATE DATABASE agent_tracer"
export DATABASE_URL=postgresql+asyncpg://$USER@localhost:5432/agent_tracer
```

### 3. Migrate, seed, run

```bash
make migrate     # alembic upgrade head
make seed        # demo account + traces; prints an SDK API key
make dev-api     # uvicorn on :8000 (hot reload)
make dev-web     # vite on :5173 (proxies /api and /v1 to :8000)
```

Open http://localhost:5173. If your API runs on a non-default port:
`VITE_API_PROXY_TARGET=http://localhost:8321 npm run dev`.

There are no separate workers — live streaming runs in-process (asyncio pub/sub)
and the SDK batches in a background thread inside *your* application.

---

## Using the Python SDK

```bash
pip install -e sdk          # from this repo (or publish agent-tracer-sdk)
```

```python
from agent_tracer import AgentTracer

tracer = AgentTracer(
    api_key="at_…",                    # or AGENT_TRACER_API_KEY
    base_url="http://localhost:8000",  # or AGENT_TRACER_BASE_URL
)

# One trace = one end-to-end run of your agent.
with tracer.trace("support-run", session_id="user-42", metadata={"env": "prod"}):
    with tracer.agent("router"):

        # Wrap a model call — record request, response, and usage.
        with tracer.llm(model="claude-opus-5", system="You are helpful.",
                        messages=[{"role": "user", "content": question}]) as llm:
            reply = client.messages.create(...)          # your existing call
            llm.set_output({"role": "assistant", "content": reply.text})
            llm.set_usage(input_tokens=reply.usage.input_tokens,
                          output_tokens=reply.usage.output_tokens)

        # Wrap a tool call.
        with tracer.tool("search", input={"q": "refund policy"}) as tool:
            tool.set_output(run_search("refund policy"))

# Or decorate existing functions (sync and async):
@tracer.observe(kind="TOOL")
def lookup_order(order_id: str): ...
```

Spans record exceptions automatically (type, message, stack trace), mark the span
and trace as errored, and re-raise. Also available: `tracer.chain()`,
`tracer.retriever()`, `span.set_attribute()`, `span.add_event()`,
`tracer.flush()` for short-lived scripts, and `agent_tracer.current_span()`.
Telemetry is exported by a daemon thread in batches — instrumentation never
blocks your app, and the SDK degrades to a no-op if no API key is set.

**Cost tracking:** send token counts and the server prices them from a built-in
model table (Anthropic, OpenAI, and common OSS models); pass
`span.set_usage(cost_usd=…)` to override.

### Sending a sample trace without the SDK

```bash
curl -X POST http://localhost:8000/v1/ingest \
  -H "Authorization: Bearer at_…" -H "Content-Type: application/json" \
  -d '{"spans": [{"trace_id": "'"$(openssl rand -hex 16)"'",
                  "span_id": "'"$(openssl rand -hex 8)"'",
                  "name": "hello-world", "kind": "AGENT", "status": "ok",
                  "started_at": "2026-08-04T12:00:00Z",
                  "ended_at": "2026-08-04T12:00:01Z",
                  "input": {"question": "hi"}, "output": {"answer": "hello"}}]}'
```

### OpenTelemetry / OpenInference apps

Point any OTLP/HTTP JSON exporter at Agent Tracer — the default exporter path
(`<endpoint>/v1/traces`) is served natively:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer at_…"
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
```

`openinference.span.kind`, `llm.model_name`, `llm.token_count.*`,
`gen_ai.usage.*`, `input.value` / `output.value`, and exception events are all
mapped onto native fields.

---

## Running the tests

```bash
make test        # server (38) + sdk (18) + web (13)

# individually:
cd server && pytest -q                       # SQLite by default
TEST_DATABASE_URL=postgresql+asyncpg://… pytest -q   # same suite on Postgres
cd sdk && pytest -q
cd web && npm run test
make lint        # ruff over server + sdk
```

CI (GitHub Actions, `.github/workflows/ci.yml`) runs on every push/PR: lint,
server tests on SQLite **and** PostgreSQL, an Alembic upgrade/downgrade/upgrade
round-trip, SDK tests on Python 3.9 and 3.12, frontend type-check + tests +
production build, and both Docker image builds.

---

## Building for production & deploying

The Docker images are the production build:

- `server/Dockerfile` — Python 3.12-slim, non-root user, container healthcheck;
  applies migrations on boot, then serves uvicorn on :8000.
- `web/Dockerfile` — Node build stage → nginx serving the static SPA and
  reverse-proxying `/api` + `/v1` same-origin (SSE-safe: buffering off).

Deploy to any Docker host:

```bash
# on the server
git clone <repo> && cd agent-tracer
cp .env.example .env    # set a strong SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build -d
docker compose run --rm seed          # optional demo data
```

Put your TLS terminator (Caddy, Traefik, an ALB…) in front of the `web`
service — it already forwards everything the API needs. For a managed database,
point `DATABASE_URL` at it and drop the `db` service. Frontend-only builds are
`cd web && npm run build` → static files in `web/dist/`.

Production notes, already handled:

- passwords hashed with Argon2id; API keys stored as SHA-256 hashes (shown once)
- JWT (HS256) sessions; auth endpoints rate-limited per IP
- replay provider keys encrypted at rest (Fernet key derived from `SECRET_KEY`)
- share links are 256-bit random tokens, revocable, optionally expiring
- ingest payloads validated and size-capped (10 MiB / 1000 spans per batch,
  oversized values truncated, never rejected)
- security headers + restrictive CORS; `/healthz` (liveness) and `/readyz`
  (DB readiness) for orchestration
- request logging with latency; the API refuses to boot in production with the
  default secret

---

## Repository layout

```
server/   FastAPI app — api/ (routes), core/ (ingest, otlp, replay, diffing,
          events, pricing, security), models.py, seed.py, alembic/, tests/
sdk/      agent-tracer-sdk — src/agent_tracer/, examples/demo_agent.py, tests/
web/      React SPA — src/pages/, src/components/, src/lib/, src/test/
```

### Key design decisions

- **Span upserts make the live view work.** The SDK ships a span at *start*
  (status `running`) and completes it later; the server upserts by
  `(trace, span_id)` and recomputes trace aggregates in the same transaction.
  Live clients get SSE events only after commit.
- **SSE over in-process pub/sub** — no Redis/queue to operate at v1; the broker
  is a small interface that could swap to Redis for multi-worker deployments.
- **Replay is deliberately side-effect-free**: it re-executes exactly one model
  call with recorded/edited input, storing attempts separately from the trace.
  A deterministic offline simulator keeps the workflow usable without provider
  keys (and in the demo).
- **Trace comparison aligns spans by (name, kind) per tree level** — built for
  the "this run failed, that one worked, what changed?" question, surfacing
  status flips, structural drift, and input/output/latency/token deltas.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `SECRET_KEY must be set in production` on boot | Set a real `SECRET_KEY` in `.env` (see `.env.example`). |
| `set SECRET_KEY in .env` from docker compose | You skipped `cp .env.example .env`. |
| API can't reach Postgres locally | Check `DATABASE_URL` uses `postgresql+asyncpg://` and the DB exists (`createdb agent_tracer`). `pg_isready` should say *accepting connections*. |
| `password authentication failed` in Docker | You changed `POSTGRES_PASSWORD` after the volume was created — `docker compose down -v` (wipes data) or update the password inside Postgres. |
| SDK sends but nothing appears | Wrong key or URL: the SDK logs `collector rejected batch (401)` warnings. Regenerate a key in *Settings → API keys*; check `AGENT_TRACER_BASE_URL`. Revoked keys are rejected. |
| Short script exits before traces arrive | Call `tracer.flush()` (the demo script does). |
| Live badge shows *Offline* | The SSE stream reconnects automatically; if it persists behind your own proxy, disable response buffering for `/api` (see `web/nginx.conf`). |
| Vite dev server hits the wrong API port | `VITE_API_PROXY_TARGET=http://localhost:<port> npm run dev`. |
| Login says invalid email for the seeded user | Use `demo@agenttracer.dev` (address validation rejects reserved TLDs like `.local`). |
| `429 Too many attempts` on login | Per-IP rate limit on auth endpoints — wait 60s. |
| Replay says no provider key | Add one under *Settings → Replay credentials*, or pick the *Simulation* provider. |
| Port 3000/8000 already taken | Set `WEB_PORT` / `API_PORT` in `.env`. |

---

## License

MIT — see [LICENSE](LICENSE).
