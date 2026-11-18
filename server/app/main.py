import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import (
    auth,
    compare,
    datasets,
    evaluators,
    experiments,
    ingest,
    live,
    projects,
    replays,
    scores,
    shares,
    traces,
)
from app.api.deps import SESSION_COOKIE
from app.config import get_settings
from app.core import handlers  # noqa: F401  (registers job handlers)
from app.core.jobs import notify, worker_loop
from app.core.retention import retention_loop
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
    stop = asyncio.Event()
    worker: asyncio.Task | None = None
    if settings.worker_mode == "inline" and settings.environment != "test":
        worker = asyncio.create_task(worker_loop(stop, settings.worker_concurrency))
    retention = (
        asyncio.create_task(retention_loop(stop))
        if settings.trace_retention_enabled_at is not None and settings.environment != "test"
        else None
    )
    try:
        yield
    finally:
        stop.set()
        if worker is not None:
            notify()
            await worker
        if retention is not None:
            await retention
        await get_engine().dispose()
        logger.info("Agent Tracer API stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    docs_enabled = settings.environment != "production" or settings.public_api_docs
    app = FastAPI(
        title="Agent Tracer API",
        version="0.1.0",
        description="Debug and understand AI-agent executions.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
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
        is_write = request.method not in {"GET", "HEAD", "OPTIONS"}
        is_browser = SESSION_COOKIE in request.cookies or request.url.path.startswith("/api/auth/")
        if is_write and is_browser and request.url.path.startswith("/api/"):
            if request.headers.get("origin") not in settings.cors_origin_list:
                return JSONResponse({"detail": "Unapproved browser origin"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        path = getattr(request.scope.get("route"), "path", "<unmatched>")
        if path not in ("/healthz", "/readyz"):
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                path,
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
    app.include_router(scores.router)
    app.include_router(datasets.router)
    app.include_router(evaluators.router)
    app.include_router(experiments.router)

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
