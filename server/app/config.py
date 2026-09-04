from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    app_name: str = "Agent Tracer"
    environment: str = "development"  # development | production | test
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://tracer:tracer@localhost:5432/agent_tracer"
    # Secret used to sign JWTs and derive the credential-encryption key.
    # MUST be overridden in production.
    secret_key: str = "dev-only-secret-change-me"
    access_token_expire_minutes: int = 60 * 24

    # Comma-separated list of allowed CORS origins for the SPA dev server.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Ingest guardrails
    max_ingest_body_bytes: int = 10 * 1024 * 1024  # 10 MiB
    max_spans_per_batch: int = 1000

    # Auth endpoint rate limiting (per IP)
    auth_rate_limit_attempts: int = 20
    auth_rate_limit_window_seconds: int = 60

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
