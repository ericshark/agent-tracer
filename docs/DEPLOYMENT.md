# Agent Tracer deployment

- Dashboard: https://agent-tracer.ericzwierzynski.dev
- API readiness: https://agent-tracer-api.onrender.com/readyz
- Database: Supabase project `agent-tracer-prod` (`msfbgfymavjjbzndfhqf`).

Vercel builds `web/` from GitHub `main`. The browser sends API and SSE
requests directly to the Render Free service, which uses the Supabase TLS
session pooler. Set `VITE_API_BASE_URL` in Vercel and the exact dashboard
origin in Render's `CORS_ORIGINS`. Render stores `DATABASE_URL`, `SECRET_KEY`,
and the CA file referenced by `PGSSLROOTCERT`. PostgREST exposes an empty schema.

Check GitHub Actions and the provider deployment logs after pushing. For
schema changes, review and apply Alembic separately before releasing code
that depends on the schema. Roll back code in the provider dashboards only
after checking database compatibility. Free Render can sleep when idle.

The dashboard domain uses a DNS-only Cloudflare CNAME to the project-specific
Vercel DNS target. The old Vercel address remains available. The API remains at
its existing Render hostname; no API domain was changed. Add the new dashboard
origin to Render `CORS_ORIGINS` while retaining the old origin. Domain HTTPS and desktop/mobile browser loading were verified on November 16,
2026. The API CORS update is pending Render workspace confirmation required
by the connector; dashboard authentication/API requests at the new origin have
not been verified.
