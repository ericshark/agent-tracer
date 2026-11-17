# Agent Tracer reference

[Project overview and Docker setup](../README.md). Commands below start from the
repository root unless stated otherwise. API examples use port 8001; match it to
your running server.

## Live demo

Start the stack using the root README, then create a virtual environment and
install the SDK (or reuse your local development environment):

```bash
python3 -m venv .venv && .venv/bin/pip install -e sdk
export AGENT_TRACER_API_KEY='at_replace_with_your_key' # From the seed output.
export AGENT_TRACER_BASE_URL=http://localhost:8001
.venv/bin/python sdk/examples/demo_agent.py --runs 2 --fail
```

Keep the Traces page open while it runs — new runs appear and complete in real
time, and the last one fails at the tool step so you can walk the debugging flow
below.

## Debugging workflow

1. **Traces** — the project overview shows KPI tiles (volume, error rate, p95
   latency, spend), a traces-over-time chart, and the live-updating trace list.
   Click the failing `research-agent` run (✕ Error).
2. **Timeline** — the waterfall shows the span tree with per-kind colors and
   timing bars. The failed `query_metrics` tool span is marked ✕; the inspector
   opens on its **Error** tab with the exception type, message, and stack trace.
3. **Inspect the LLM call** — select the `plan` span: the **Input** tab renders
   the chat messages (system + user), **Output** the assistant reply, with model,
   token counts, and cost in the header.
4. **Replay** — on an LLM span, open **Replay** and hit _▶ Replay step_. The step
   re-runs with its recorded input — or edit the prompt first. Replays never
   execute tools and never modify the original trace. With no provider key the
   offline simulator answers; add an Anthropic/OpenAI key under _Settings →
   Replay credentials_ to replay against the real model.
5. **Compare** — back on the trace list, press _Compare_ on the failed run, then
   on a successful one. The diff aligns both span trees and shows what changed:
   status flips, missing steps, output/input drift, latency/token/cost deltas.
6. **Share** — from a trace, _Share → Create link_ mints a revocable, optionally
   expiring read-only URL (`/share/<256-bit-token>`) that renders the full trace
   without an account.

## Local development (without Docker)

Prerequisites: Python 3.11+, Node.js 22.12+, npm, and make. The example below
uses SQLite; PostgreSQL 14+ is also supported.

### Install dependencies

```bash
make install
```

This creates the root `.venv`, installs the server and SDK with development
dependencies, and installs web dependencies. The manual equivalent is:

```bash
python3 -m venv .venv
.venv/bin/pip install -e "server[dev]" -e "sdk[dev]"
(cd web && npm ci)
```

### Configure the API

Create `server/.env` with:

```dotenv
DATABASE_URL=sqlite+aiosqlite:///dev.db
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174
```

The local API and migration commands run from `server/`, so the SQLite database
is `server/dev.db`. They read `server/.env`; Docker Compose instead reads the
root `.env`. Exported environment variables override file values.

| Variable       | Default                                                          | Purpose                                                        |
| -------------- | ---------------------------------------------------------------- | -------------------------------------------------------------- |
| `DATABASE_URL` | `postgresql+asyncpg://tracer:tracer@localhost:5432/agent_tracer` | Async SQLAlchemy connection URL; SQLite also works.            |
| `SECRET_KEY`   | `dev-only-secret-change-me`                                      | Signs JWTs and encrypts provider keys; replace for production. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`                    | Comma-separated allowed frontend origins.                      |
| `ENVIRONMENT`  | `development`                                                    | Production rejects the default secret.                         |
| `LOG_LEVEL`    | `INFO`                                                           | Backend log verbosity.                                         |
| `WORKER_MODE`  | `inline`                                                         | `inline` runs background jobs in the API process; `external` expects `python -m app.worker`; `off` disables them. |

For PostgreSQL, create the database with `createdb agent_tracer` using your local
PostgreSQL tools and credentials. Replace the SQLite URL in `server/.env` with
`postgresql+asyncpg://USER:PASSWORD@localhost:5432/agent_tracer`, using your database
username and password.

### Migrate, seed, and run

```bash
make migrate
make seed
```

Seeding prints the demo login and a fresh SDK API key.

In terminal 1, from the repository root:

```bash
cd server
../.venv/bin/python -m uvicorn app.main:app --reload --port 8001
```

In terminal 2, from the repository root:

```bash
cd web
VITE_API_PROXY_TARGET=http://localhost:8001 npm run dev -- --port 5174
```

Open the URL Vite prints. If a port is occupied, increment it, updating
`VITE_API_PROXY_TARGET` for an API change and `CORS_ORIGINS` for a frontend change.
Stop both servers with Ctrl+C. The `make dev-api` and `make dev-web` shortcuts
use ports 8000 and 5173; the explicit commands above select the development ports.

No broker is required: live streaming uses in-process asyncio pub/sub, the SDK
batches in a background thread inside the instrumented application, and
background jobs are rows in the `jobs` table run by a worker inside the API
process. To move them out of the API process, set `WORKER_MODE=external` and run
`cd server && ../.venv/bin/python -m app.worker`.

## Using the Python SDK

See the [SDK quick start](../sdk/README.md) for installation, environment
configuration, and a complete example. A trace represents one agent run; nested
`agent`, `llm`, and `tool` spans describe its steps.

The SDK uses W3C-format trace/span IDs and depends only on `httpx`. Trace options
include `session_id` and `metadata`; use `tracer.span(kind=...)` for a generic span.

To wrap an existing model call, use this integration pattern inside a trace.
`messages`, `model_name`, and `call_model` come from your application; adapt the
response fields to your provider's SDK:

```python
with tracer.llm(model=model_name, messages=messages) as llm:
    reply = call_model(messages)
    llm.set_output({"role": "assistant", "content": reply.text})
    llm.set_usage(
        input_tokens=reply.usage.input_tokens,
        output_tokens=reply.usage.output_tokens,
    )
```

The decorator form wraps existing synchronous or asynchronous functions:

```python
@tracer.observe(kind="TOOL")
def lookup_order(order_id: str):
    return orders[order_id]  # Your application's order store.
```

Spans record exceptions automatically (type, message, stack trace), mark the span
and trace as errored, and re-raise. Also available: `tracer.chain()`,
`tracer.retriever()`, `span.set_attribute()`, `span.add_event()`,
`tracer.flush()` for short-lived scripts, and `agent_tracer.current_span()`.
Telemetry is exported by a daemon thread in batches. Call `tracer.flush()` and
`tracer.shutdown()` before a short script exits. The SDK becomes a no-op if no
API key is set.

**Cost tracking:** send token counts and the server prices them from a built-in
model table (Anthropic, OpenAI, and common OSS models); pass
`span.set_usage(cost_usd=…)` to override. `input_tokens` means uncached input:
report `cache_read_tokens` and `cache_creation_tokens` separately so they are
priced at cache rates. Add or override a model's price per project with
`PUT /api/projects/{id}/model-prices` (matched by model-name prefix).

**Slicing dimensions:** `tracer.trace(..., user_id=, tags=, environment=,
release=)` — or set `AGENT_TRACER_ENVIRONMENT` / `AGENT_TRACER_RELEASE` once.
The trace list filters on `user_id` and `environment`. For streamed model calls,
`span.mark_first_token()` records time-to-first-token.

**Scores:** attach quality signals — a number, a boolean, or a label — to a
span or a whole trace. They show up as chips on the trace list, in the span
inspector's **Scores** tab (where you can also annotate by hand), and as trends
in the overview's Quality card.

```python
with tracer.trace("support-run") as trace:
    with tracer.llm(model=model_name, messages=messages) as llm:
        ...
        llm.score("groundedness", 0.92)
    trace.score("resolved", True)

# Later, e.g. when the user clicks thumbs-down (idempotent via external_id):
tracer.score("user_feedback", False, trace_id=saved_trace_id, external_id=feedback_id)
```

Without the SDK, `POST /v1/scores` with `{"trace_id", "name", "value"}` and a
key that has the `write` scope. Filter the trace list by score with
`?score_name=…&score_min=…&score_max=…`.

**API key scopes:** keys carry `ingest`, `read` and `write` scopes (all three by
default). Create an ingest-only key for production services by passing
`"scopes": ["ingest"]` when creating the key.

### Sending a sample trace without the SDK

Requires curl and OpenSSL. Replace the placeholder API key with your own.

```bash
curl -X POST http://localhost:8001/v1/ingest \
  -H "Authorization: Bearer at_…" -H "Content-Type: application/json" \
  -d '{"spans": [{"trace_id": "'"$(openssl rand -hex 16)"'",
                  "span_id": "'"$(openssl rand -hex 8)"'",
                  "name": "hello-world", "kind": "AGENT", "status": "ok",
                  "started_at": "2026-08-04T12:00:00Z",
                  "ended_at": "2026-08-04T12:00:01Z",
                  "input": {"question": "hi"}, "output": {"answer": "hello"}}]}'
```

### OpenTelemetry / OpenInference apps

Point an [OpenInference](https://github.com/Arize-ai/openinference) or other
OTLP/HTTP JSON exporter at Agent Tracer — the default exporter path
(`<endpoint>/v1/traces`) is served natively:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8001
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer at_…"
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
```

`openinference.span.kind`, `llm.model_name`, `llm.token_count.*`,
`gen_ai.usage.*`, `input.value` / `output.value`, and exception events are all
mapped onto native fields.

## Running the tests

After installing local development dependencies:

```bash
make test        # All suites.
make lint        # Ruff over server and SDK.
make test-server # Server tests; SQLite by default.
make test-sdk    # SDK tests.
make test-web    # Frontend tests.
(cd web && npm run build) # Includes TypeScript checks.
```

To run server tests against PostgreSQL instead, set `TEST_DATABASE_URL` to a
PostgreSQL test database, then run `make test-server`.

CI (GitHub Actions, `.github/workflows/ci.yml`) runs on every push/PR: lint,
server tests on SQLite **and** PostgreSQL, an Alembic upgrade/downgrade/upgrade
round-trip, SDK tests on Python 3.9 and 3.12, frontend type-check + tests +
production build, and both Docker image builds.

## Building for production & deploying

The Docker images are the production build:

- `server/Dockerfile` — Python 3.12-slim, non-root user, container healthcheck;
  applies migrations on boot, then serves uvicorn on :8000.
- `web/Dockerfile` — Node build stage → nginx serving the static SPA and
  reverse-proxying `/api` + `/v1` same-origin (SSE-safe: buffering off).

On a Docker host, use the [Docker setup](../README.md#run-locally). Set a strong
`SECRET_KEY` and `POSTGRES_PASSWORD` in the root `.env`; change `DEMO_PASSWORD`
if you seed demo data. Generate a secret with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Put your TLS terminator (Caddy, Traefik, an ALB…) in front of the `web`
service — it already forwards everything the API needs. For a managed database,
update the API service's `DATABASE_URL` in `docker-compose.yml` and remove the
`db` service and its dependencies. The existing Compose file constructs its
connection URL directly; setting `DATABASE_URL` in the root `.env` alone does
not override it. Frontend-only builds are
`cd web && npm run build` → static files in `web/dist/`.

Production behavior:

- passwords hashed with Argon2id; API keys stored as SHA-256 hashes (shown once)
- JWT (HS256) sessions; auth endpoints rate-limited per IP
- replay provider keys encrypted at rest (Fernet key derived from `SECRET_KEY`)
- share links are 256-bit random tokens, revocable, optionally expiring
- ingest payloads validated and size-capped (10 MiB / 1000 spans per batch,
  oversized individual values truncated)
- security headers + restrictive CORS; `/healthz` (liveness) and `/readyz`
  (DB readiness) for orchestration
- request logging with latency; the API refuses to boot in production with the
  default secret

## Layout and design decisions

```text
server/   FastAPI app — api/ (routes), core/ (ingest, otlp, replay, diffing,
          events, pricing, security), models.py, seed.py, alembic/, tests/
sdk/      agent-tracer-sdk — src/agent_tracer/, examples/demo_agent.py, tests/
web/      React SPA — src/pages/, src/components/, src/lib/, src/test/
```

### Key design decisions

- **Span upserts make the live view work.** The SDK ships a span at _start_
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

## Troubleshooting

| Symptom                                        | Fix                                                                                                                                                                            |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `SECRET_KEY must be set in production` on boot | Set a real `SECRET_KEY` in `.env` (see `.env.example`).                                                                                                                        |
| `set SECRET_KEY in .env` from docker compose   | You skipped `cp .env.example .env`.                                                                                                                                            |
| API can't reach Postgres locally               | Check `DATABASE_URL` uses `postgresql+asyncpg://` and the DB exists (`createdb agent_tracer`). `pg_isready` should say _accepting connections_.                                |
| `password authentication failed` in Docker     | Changing `POSTGRES_PASSWORD` does not update an existing database volume. Restore the prior value or update the database role's password inside PostgreSQL.                    |
| SDK sends but nothing appears                  | Wrong key or URL: the SDK logs `collector rejected batch (401)` warnings. Regenerate a key in _Settings → API keys_; check `AGENT_TRACER_BASE_URL`. Revoked keys are rejected. |
| Short script exits before traces arrive        | Call `tracer.flush()` (the demo script does).                                                                                                                                  |
| Live badge shows _Offline_                     | The SSE stream reconnects automatically; if it persists behind your own proxy, disable response buffering for `/api` (see `web/nginx.conf`).                                   |
| Vite dev server hits the wrong API port        | From `web/`, set `VITE_API_PROXY_TARGET` to the API URL and run `npm run dev -- --port 5174`.                                                                                  |
| Login says invalid email for the seeded user   | Use `demo@agenttracer.dev` (address validation rejects reserved TLDs like `.local`).                                                                                           |
| `429 Too many attempts` on login               | Per-IP rate limit on auth endpoints — wait 60s.                                                                                                                                |
| Replay says no provider key                    | Add one under _Settings → Replay credentials_, or pick the _Simulation_ provider.                                                                                              |
| Docker host port already taken                 | Set `WEB_PORT` / `API_PORT` in `.env`.                                                                                                                                         |

### Vercel, Render, and Supabase

Connect both hosting projects to GitHub `main`. Vercel uses the `web/` root
and its Vite preset. Set `VITE_API_BASE_URL` to the public Render origin so both
HTTP requests and live events reach the same backend. The Render Blueprint
builds from `server/` and starts one worker on Render Free. Run the reviewed
Alembic migrations separately before deploying a revision that needs them. Set
`CORS_ORIGINS` to the production Vercel origin and keep the generated
`SECRET_KEY` stable across deployments.

Use a dedicated Supabase project with its Data API disabled. Set Render's
`DATABASE_URL` to the asyncpg session-pooler URL with verified TLS
(`ssl=verify-full`). Keep that URL in Render secrets. Review the migration
before releasing and verify `/readyz`, cross-account isolation, an SDK ingest,
a dashboard live update, and simulated replay before inviting users. Render Free
sleeps after inactivity, so the first request can take about a minute.
