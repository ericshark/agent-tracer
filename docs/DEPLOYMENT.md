# Agent Tracer deployment

- Dashboard: https://agent-tracer.ericzwierzynski.dev
- API readiness: https://agent-tracer-api.onrender.com/readyz
- Database: Supabase project `agent-tracer-prod` (`msfbgfymavjjbzndfhqf`).

Vercel builds `web/` from GitHub `main`. For the browser-session release,
`web/vercel.json` proxies browser API and streaming requests to Render from the
dashboard origin. The SDK continues to use the Render URL with a project key.
Set each exact dashboard origin in Render's `CORS_ORIGINS`. Render uses the
Supabase TLS session pooler and stores `DATABASE_URL`, `SECRET_KEY`,
and the CA file referenced by `PGSSLROOTCERT`. PostgREST exposes an empty schema.

Check GitHub Actions and the provider deployment logs after pushing. For
schema changes, review and apply Alembic separately before releasing code
that depends on the schema. Roll back code in the provider dashboards only
after checking database compatibility. Free Render can sleep when idle.

The dashboard domain uses a DNS-only Cloudflare CNAME to the project-specific
Vercel DNS target. The old Vercel address remains available. The API remains at
its existing Render hostname; no API domain was changed. Render `CORS_ORIGINS` includes both
`https://agent-tracer.ericzwierzynski.dev` and the old Vercel origin. Domain HTTPS
and desktop/mobile browser loading were verified on November 16, 2026.
The CORS update deploys through Render; verify `/readyz` and an OPTIONS request
with the new dashboard Origin header after deployment. Authenticated user flows
were not tested during the domain change.

## Background jobs and evals

Experiments run as database-backed jobs executed by a worker inside the API
process (`WORKER_MODE=inline`, the default), so no extra service is needed on
Render Free. Judge and replay calls use per-project provider keys stored under
Settings; without one the built-in simulator runs. Migrations are applied by hand
before releasing code that needs them: the evals release added
`0125979a5867`, `d643b3c0f62e`, `35d122a88892` and `87e42d38c899`, applied to
production on November 17, 2026 before the code deployed.

## Browser session and privacy rollout

Coordinate the Vercel and Render release. Review and apply Alembic revision
`9c6d0139c8ef` before deploying app code that requires it. This backfills legacy
share expiration and creates the browser session table. The backfill remains
in place after downgrading. Existing browsers must sign in again. New share
links put their credential in the browser fragment and submit it in a JSON body.
Legacy path links are supported until expiration. Keep access logs disabled on
Render and verify proxy logs and header forwarding before enabling the release.
Verify an account sign-in, sign-out, sanitized share, and live subscription
through the public dashboard origin. Remove the obsolete `VITE_API_BASE_URL`
setting after the coordinated deployment.

Keep `TRACE_RETENTION_ENABLED_AT` unset until separately authorized. On
activation set it to the actual UTC activation time in RFC 3339. The daily
cleanup starts once 30 days have passed, then removes traces older than 30 days,
along with their spans, shares, and trace-linked results. Dataset copies retain
their own lifecycle. Password-confirmed account deletion removes owned
projects, datasets and related credentials. Existing backups remain subject to
the provider's backup retention.

The Render service must install `requirements.lock` with hash verification before
installing the app with `--no-deps`. Match the reviewed Render Blueprint build and
start commands in existing dashboard configuration. Custom provider hosts must
be trusted by the operator, reviewed for DNS and network egress, and explicitly
listed in `OPENAI_PROVIDER_HOSTS` or `ANTHROPIC_PROVIDER_HOSTS`. The official
provider endpoints work with neither setting. Keep `PUBLIC_API_DOCS` unset
unless interactive documentation is intended to be public.
