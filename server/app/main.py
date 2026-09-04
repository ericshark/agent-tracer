import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, compare, ingest, live, projects, replays, shares, traces
from app.config import get_settings
from app.db import get_engine
from app.logging_config import configure_logging

logger = logging.getLogger("agent_tracer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Agent Tracer API starting (env=%s)", settings.environment)
    if settings.environment == "production" and settings.secret_key == "dev-only-secret-change-me":
        raise RuntimeError("SECRET_KEY must be set in production")
    yield
    await get_engine().dispose()
    logger.info("Agent Tracer API stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Agent Tracer API",
        version="0.1.0",
        description="Debug and understand AI-agent executions.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers_and_logging(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path not in ("/healthz", "/readyz"):
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        return response

    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(traces.router)
    app.include_router(ingest.router)
    app.include_router(live.router)
    app.include_router(replays.router)
    app.include_router(compare.router)
    app.include_router(shares.router)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict:
        """Liveness: the process is up."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz() -> dict:
        """Readiness: the database is reachable."""
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            logger.error("Readiness check failed: %s", exc)
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail="database unavailable") from exc
        return {"status": "ready"}

    return app


app = create_app()
