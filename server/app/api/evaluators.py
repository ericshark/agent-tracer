import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import can_access, load_trace
from app.api.deps import get_current_user, get_owned_project
from app.core.evals.base import EvalConfigError
from app.core.evals.registry import TEMPLATES, run_evaluator, validate_config
from app.core.experiments import context_for_trace
from app.core.llm import load_credentials
from app.core.scores import publish_score, upsert_score
from app.db import get_db
from app.models import Evaluator, Project, Span, Trace, User
from app.schemas.experiments import (
    DryRun,
    EvalResultOut,
    EvaluateTrace,
    EvaluatorCreate,
    EvaluatorOut,
    EvaluatorUpdate,
    TemplateOut,
)
from app.schemas.scores import ScoreBase

router = APIRouter(prefix="/api", tags=["evaluators"])


@router.get("/evaluator-templates", response_model=list[TemplateOut])
async def list_templates(_: User = Depends(get_current_user)) -> list[TemplateOut]:
    """The built-in evaluator catalog: deterministic checks, trajectory checks, LLM judges."""
    out = []
    for template in TEMPLATES.values():
        data = asdict(template)
        data.pop("run")
        out.append(TemplateOut(**data))
    return out


def _check(template: str, config: dict) -> None:
    try:
        validate_config(template, config)
    except EvalConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


async def _load(db: AsyncSession, user: User, evaluator_id: uuid.UUID) -> Evaluator:
    result = await db.execute(
        select(Evaluator)
        .join(Project, Evaluator.project_id == Project.id)
        .where(Evaluator.id == evaluator_id, can_access(user))
    )
    evaluator = result.scalar_one_or_none()
    if evaluator is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluator not found")
    return evaluator


async def _name_taken(db: AsyncSession, project_id: uuid.UUID, name: str) -> bool:
    result = await db.execute(
        select(Evaluator.id).where(Evaluator.project_id == project_id, Evaluator.name == name)
    )
    return result.first() is not None


@router.get("/projects/{project_id}/evaluators", response_model=list[EvaluatorOut])
async def list_evaluators(
    project: Project = Depends(get_owned_project), db: AsyncSession = Depends(get_db)
) -> list[EvaluatorOut]:
    result = await db.execute(
        select(Evaluator).where(Evaluator.project_id == project.id).order_by(Evaluator.name)
    )
    return [EvaluatorOut.model_validate(e) for e in result.scalars()]


@router.post(
    "/projects/{project_id}/evaluators",
    response_model=EvaluatorOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluator(
    payload: EvaluatorCreate,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> EvaluatorOut:
    _check(payload.template, payload.config)
    if await _name_taken(db, project.id, payload.name):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"An evaluator named {payload.name!r} already exists"
        )
    evaluator = Evaluator(
        project_id=project.id, name=payload.name, template=payload.template, config=payload.config
    )
    db.add(evaluator)
    await db.commit()
    await db.refresh(evaluator)
    return EvaluatorOut.model_validate(evaluator)


@router.patch("/evaluators/{evaluator_id}", response_model=EvaluatorOut)
async def update_evaluator(
    evaluator_id: uuid.UUID,
    payload: EvaluatorUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvaluatorOut:
    evaluator = await _load(db, user, evaluator_id)
    if payload.config is not None:
        _check(evaluator.template, payload.config)
        evaluator.config = payload.config
    if payload.name is not None and payload.name != evaluator.name:
        if await _name_taken(db, evaluator.project_id, payload.name):
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"An evaluator named {payload.name!r} already exists"
            )
        evaluator.name = payload.name
    await db.commit()
    await db.refresh(evaluator)
    return EvaluatorOut.model_validate(evaluator)


@router.delete("/evaluators/{evaluator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluator(
    evaluator_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    evaluator = await _load(db, user, evaluator_id)
    await db.delete(evaluator)
    await db.commit()


def _pick_span(trace: Trace, span_pk: uuid.UUID | None) -> Span | None:
    if span_pk is None:
        return None
    span = next((s for s in trace.spans if s.id == span_pk), None)
    if span is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Span not found")
    return span


@router.post("/projects/{project_id}/evaluators/dry-run", response_model=EvalResultOut)
async def dry_run(
    payload: DryRun,
    project: Project = Depends(get_owned_project),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvalResultOut:
    """Run an evaluator configuration against a recorded trace. Nothing is saved."""
    _check(payload.template, payload.config)
    trace = await load_trace(db, user, payload.trace_pk)
    if trace.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    ctx = context_for_trace(trace, _pick_span(trace, payload.span_pk), payload.expected)
    creds = await load_credentials(db, project.id)
    try:
        result = await run_evaluator(payload.template, payload.config, ctx, creds)
    except Exception as exc:  # provider/network failure
        return EvalResultOut(
            value=None, data_type="numeric", error=f"{type(exc).__name__}: {exc}"[:1000]
        )
    return EvalResultOut(
        value=result.value, data_type=result.data_type, comment=result.comment, error=result.error
    )


@router.post("/traces/{trace_pk}/evaluate", response_model=list[EvalResultOut])
async def evaluate_trace(
    trace_pk: uuid.UUID,
    payload: EvaluateTrace,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EvalResultOut]:
    """Run saved evaluators on a trace (or one of its spans) and store the scores."""
    trace = await load_trace(db, user, trace_pk)
    span = _pick_span(trace, payload.span_pk)
    result = await db.execute(
        select(Evaluator).where(
            Evaluator.project_id == trace.project_id, Evaluator.id.in_(payload.evaluator_ids)
        )
    )
    evaluators = sorted(result.scalars(), key=lambda e: e.name)
    if len(evaluators) != len(set(payload.evaluator_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluator not found")

    ctx = context_for_trace(trace, span)
    creds = await load_credentials(db, trace.project_id)
    out, saved = [], []
    for evaluator in evaluators:
        try:
            res = await run_evaluator(evaluator.template, evaluator.config, ctx, creds)
        except Exception as exc:
            out.append(
                EvalResultOut(
                    name=evaluator.name,
                    value=None,
                    data_type="numeric",
                    error=f"{type(exc).__name__}: {exc}"[:1000],
                )
            )
            continue
        out.append(
            EvalResultOut(
                name=evaluator.name,
                value=res.value,
                data_type=res.data_type,
                comment=res.comment,
                error=res.error,
            )
        )
        if res.error is None and res.value is not None:
            saved.append(
                await upsert_score(
                    db,
                    project_id=trace.project_id,
                    trace_pk=trace.id,
                    span_pk=span.id if span else None,
                    data=ScoreBase(
                        name=evaluator.name,
                        value=res.value,
                        data_type=res.data_type,
                        comment=res.comment,
                        metadata=res.metadata,
                    ),
                    source="evaluator",
                )
            )
    await db.commit()
    for score in saved:
        await db.refresh(score)
        publish_score(score)
    return out
