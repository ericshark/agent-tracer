# Agent Tracer

A tool for inspecting AI-agent runs: model and tool calls, timing, token usage,
cost, and errors. It provides live traces, model-call replay, run comparison,
and read-only sharing.

## Run locally

Requires Docker with the Compose plugin. From the repository root:

```bash
cp .env.example .env
```

Edit `.env`: set a long random `SECRET_KEY`, `WEB_PORT=3001`, and `API_PORT=8001`.
If either port is occupied, increment it. Then start and seed the stack:

```bash
docker compose up --build -d
docker compose run --rm seed
```

Open <http://localhost:3001> and sign in with `demo@agenttracer.dev` and
`demo-password` (or your `DEMO_PASSWORD`). The seed command prints an SDK API
key and creates the Travel Concierge demo project. API docs are at
<http://localhost:8001/docs>; adjust both URLs if you changed ports.

Use `docker compose down` to stop the stack; database data stays in its volume.
For development without Docker, see the [local setup](docs/reference.md#local-development-without-docker).

## Useful commands

After the local development dependencies are installed:

- `make test`: run server, SDK, and web tests.
- `make lint`: lint Python code.
- `cd web && npm run build`: type-check and build the frontend.

## How it works

- `sdk/`: Python instrumentation that batches traces in a background thread.
- `server/`: FastAPI ingestion, authentication, replay, comparison, and storage;
  Alembic manages database migrations.
- `web/`: React interface with live updates over Server-Sent Events.
- Docker Compose runs PostgreSQL, the API, and an nginx-served frontend.

The API accepts native traces and OTLP/HTTP JSON. Replay runs a single model
call without executing tools or changing the original trace; simulation works
without provider credentials.

See the [SDK quick start](sdk/README.md) and [reference](docs/reference.md) for
the demo workflow, configuration, integrations, deployment, and troubleshooting.

Licensed under [MIT](LICENSE).
