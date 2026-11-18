from functools import lru_cache

from pydantic import AwareDatetime
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_name: str = "Agent Tracer"
    environment: str = "development"  # development | production | test
    log_level: str = "INFO"
    public_api_docs: bool = False
    trace_retention_enabled_at: AwareDatetime | None = None
    openai_provider_hosts: str = ""
    anthropic_provider_hosts: str = ""

    database_url: str = "postgresql+asyncpg://tracer:tracer@localhost:5432/agent_tracer"
    # Secret used to derive the credential-encryption key.
    # MUST be overridden in production.
    secret_key: str = "dev-only-secret-change-me"

    # Comma-separated list of allowed CORS origins for the SPA dev server.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Ingest guardrails
    max_ingest_body_bytes: int = 10 * 1024 * 1024  # 10 MiB
    max_spans_per_batch: int = 1000
    ingest_rate_limit_batches: int = 120
    ingest_rate_limit_window_seconds: int = 60

    # Auth endpoint rate limiting (per IP)
    auth_client_ip_header: str | None = None
    auth_rate_limit_attempts: int = 20
    auth_rate_limit_window_seconds: int = 60

    # Background jobs: "inline" runs the worker inside the API process,
    # "external" expects `python -m app.worker`, "off" disables it.
    worker_mode: str = "inline"
    worker_concurrency: int = 2

    # Model used by LLM-judge evaluators unless an evaluator overrides it.
    default_judge_model: str = "claude-opus-5-5"
    # Model calls made in parallel by one experiment run.
    experiment_concurrency: int = 4

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Driver-less URL for Alembic (which uses a sync engine)."""
        return (
            self.database_url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
