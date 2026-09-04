import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ingest_project
from app.config import get_settings
from app.core.ingest import ingest_batch
from app.core.otlp import otlp_to_spans
from app.db import get_db
from app.models import Project
from app.schemas.ingest import IngestRequest, IngestResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])


def _check_body_size(request: Request) -> None:
    length = request.headers.get("content-length")
    if length and int(length) > get_settings().max_ingest_body_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Ingest payload too large"
        )


@router.post("/v1/ingest", response_model=IngestResponse)
async def ingest_native(
    payload: IngestRequest,
    request: Request,
    project: Project = Depends(get_ingest_project),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """Native ingest endpoint used by the Agent Tracer Python SDK."""
    _check_body_size(request)
    if len(payload.spans) > get_settings().max_spans_per_batch:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Batch exceeds {get_settings().max_spans_per_batch} spans",
        )
    traces, spans = await ingest_batch(db, project, payload.traces, payload.spans)
    return IngestResponse(accepted_traces=traces, accepted_spans=spans)


@router.post("/v1/traces")
async def ingest_otlp(
    request: Request,
    project: Project = Depends(get_ingest_project),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """OTLP/HTTP JSON endpoint (the default path for OTel OTLP HTTP exporters).

    Accepts an ExportTraceServiceRequest and maps OpenInference / gen_ai
    semantic conventions onto native spans.
    """
    _check_body_size(request)
    try:
        body = await request.json()
    except Exception as exc:  # malformed JSON
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OTLP JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OTLP JSON body")

    spans = otlp_to_spans(body)
    if len(spans) > get_settings().max_spans_per_batch:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Batch exceeds {get_settings().max_spans_per_batch} spans",
        )
    await ingest_batch(db, project, [], spans)
    # OTLP success response shape
    return {"partialSuccess": {}}
