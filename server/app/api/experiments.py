import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import can_access
from app.api.deps import (
    get_current_user,
    get_owned_project,
    get_read_project,
    get_write_project,
)
from app.core.experiments import JOB_KIND, compare_experiments, item_progress
from app.core.jobs import enqueue, notify
from app.db import get_db
from app.models import Dataset, DatasetItem, Evaluator, Experiment, ExperimentItem, Project, User
from app.schemas.experiments import (
    ExperimentCreate,
    ExperimentItemList,
    ExperimentItemOut,
    ExperimentOut,
    SdkExperimentCreate,
    SdkExperimentItems,
)

router = APIRouter(tags=["experiments"])

MAX_COMPARE = 6


async def _outs(db: AsyncSession, experiments: list[Experiment]) -> list[ExperimentOut]:
    progress = await item_progress(db, [e.id for e in experiments])
    outs = []
    for experiment in experiments:
        out = ExperimentOut.model_validate(experiment)
        out.item_count, out.completed_count = progress.get(experiment.id, (0, 0))
        outs.append(out)
    return outs


async def _out(db: AsyncSession, experiment: Experiment) -> ExperimentOut:
    return (await _outs(db, [experiment]))[0]


async def _load(db: AsyncSession, user: User, experiment_id: uuid.UUID) -> Experiment:
    result = await db.execute(
        select(Experiment)
        .join(Project, Experiment.project_id == Project.id)
        .where(Experiment.id == experiment_id, can_access(user))
    )
    experiment = result.scalar_one_or_none()
    if experiment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return experiment


async def _start(db: AsyncSession, experiment: Experiment) -> None:
    await enqueue(
        db,
        JOB_KIND,
        {"experiment_id": str(experiment.id)},
        project_id=experiment.project_id,
        dedupe_key=f"experiment:{experiment.id}",
    )
    await db.commit()
    notify()


# ------------------------------------------------------------------- dashboard


@router.get("/api/projects/{project_id}/experiments", response_model=list[ExperimentOut])
async def list_experiments(
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
    dataset_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[ExperimentOut]:
    query = select(Experiment).where(Experiment.project_id == project.id)
    if dataset_id is not None:
        query = query.where(Experiment.dataset_id == dataset_id)
    result = await db.execute(query.order_by(Experiment.created_at.desc()).limit(limit))
    return await _outs(db, list(result.scalars()))


@router.post(
    "/api/projects/{project_id}/experiments",
    response_model=ExperimentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(
    payload: ExperimentCreate,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    """Run a model/prompt over every test case in a dataset, in the background."""
    dataset = await db.get(Dataset, payload.dataset_id)
    if dataset is None or dataset.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    if payload.evaluator_ids:
        found = await db.execute(
            select(func.count())
            .select_from(Evaluator)
            .where(Evaluator.project_id == project.id, Evaluator.id.in_(payload.evaluator_ids))
        )
        if found.scalar_one() != len(set(payload.evaluator_ids)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluator not found")
    cases = (
        (
            await db.execute(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == dataset.id, DatasetItem.archived_at.is_(None))
                .order_by(DatasetItem.created_at, DatasetItem.id)
            )
        )
        .scalars()
        .all()
    )
    if not cases:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The dataset has no test cases")

    experiment = Experiment(
        project_id=project.id,
        dataset_id=dataset.id,
        name=payload.name,
        description=payload.description,
        target=payload.target.model_dump(exclude_none=True),
        evaluator_ids=[str(e) for e in payload.evaluator_ids],
        meta=payload.metadata,
    )
    db.add(experiment)
    await db.flush()
    db.add_all(
        ExperimentItem(
            experiment_id=experiment.id,
            project_id=project.id,
            dataset_item_id=case.id,
            input=case.input,
            expected_output=case.expected_output,
        )
        for case in cases
    )
    await _start(db, experiment)
    return await _out(db, experiment)


@router.get("/api/experiments/compare")
async def compare(
    ids: str = Query(..., description="Comma-separated experiment ids; the first is the baseline"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        experiment_ids = [uuid.UUID(part) for part in ids.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid experiment id") from exc
    if not 2 <= len(experiment_ids) <= MAX_COMPARE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Pick between 2 and {MAX_COMPARE} experiments"
        )
    experiments = [await _load(db, user, experiment_id) for experiment_id in experiment_ids]
    if len({e.project_id for e in experiments}) != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Experiments are in different projects")
    result = await db.execute(
        select(ExperimentItem)
        .where(ExperimentItem.experiment_id.in_(experiment_ids))
        .order_by(ExperimentItem.created_at, ExperimentItem.id)
    )
    by_experiment: dict[uuid.UUID, list[ExperimentItem]] = {}
    for item in result.scalars():
        by_experiment.setdefault(item.experiment_id, []).append(item)
    return {
        "experiments": [o.model_dump(mode="json") for o in await _outs(db, experiments)],
        **compare_experiments(experiments, by_experiment),
    }


@router.get("/api/experiments/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(
    experiment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    return await _out(db, await _load(db, user, experiment_id))


@router.get("/api/experiments/{experiment_id}/items", response_model=ExperimentItemList)
async def list_experiment_items(
    experiment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ExperimentItemList:
    experiment = await _load(db, user, experiment_id)
    query = select(ExperimentItem).where(ExperimentItem.experiment_id == experiment.id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    result = await db.execute(
        query.order_by(ExperimentItem.created_at, ExperimentItem.id).limit(limit).offset(offset)
    )
    return ExperimentItemList(
        items=[ExperimentItemOut.model_validate(i) for i in result.scalars()],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/api/experiments/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experiment(
    experiment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    experiment = await _load(db, user, experiment_id)
    await db.delete(experiment)
    await db.commit()


# ------------------------------------------------------------- SDK-facing (/v1)


async def _load_v1(db: AsyncSession, project: Project, experiment_id: uuid.UUID) -> Experiment:
    experiment = await db.get(Experiment, experiment_id)
    if experiment is None or experiment.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return experiment


@router.post("/v1/experiments", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
async def create_experiment_v1(
    payload: SdkExperimentCreate,
    project: Project = Depends(get_write_project),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    """Open an experiment whose task runs in your own process. Upload results
    with `/items`, then call `/complete` to run server-side evaluators."""
    dataset_id = None
    if payload.dataset:
        dataset_id = (
            await db.execute(
                select(Dataset.id).where(
                    Dataset.project_id == project.id, Dataset.name == payload.dataset
                )
            )
        ).scalar_one_or_none()
        if dataset_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Dataset {payload.dataset!r} not found")
    evaluator_ids: list[str] = []
    if payload.evaluators:
        result = await db.execute(
            select(Evaluator).where(
                Evaluator.project_id == project.id, Evaluator.name.in_(payload.evaluators)
            )
        )
        by_name = {e.name: e for e in result.scalars()}
        missing = [n for n in payload.evaluators if n not in by_name]
        if missing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"Unknown evaluators: {', '.join(missing)}"
            )
        evaluator_ids = [str(by_name[n].id) for n in payload.evaluators]
    experiment = Experiment(
        project_id=project.id,
        dataset_id=dataset_id,
        name=payload.name,
        description=payload.description,
        status="running",
        target={"type": "sdk"},
        evaluator_ids=evaluator_ids,
        meta=payload.metadata,
    )
    db.add(experiment)
    await db.commit()
    return await _out(db, experiment)


@router.post("/v1/experiments/{experiment_id}/items", status_code=status.HTTP_201_CREATED)
async def add_experiment_items_v1(
    experiment_id: uuid.UUID,
    payload: SdkExperimentItems,
    project: Project = Depends(get_write_project),
    db: AsyncSession = Depends(get_db),
) -> dict:
    experiment = await _load_v1(db, project, experiment_id)
    if experiment.target.get("type") != "sdk" or experiment.status != "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "This experiment is not accepting results")
    known_cases: set[uuid.UUID] = set()
    wanted = {i.dataset_item_id for i in payload.items if i.dataset_item_id is not None}
    if wanted:
        result = await db.execute(
            select(DatasetItem.id).where(
                DatasetItem.project_id == project.id, DatasetItem.id.in_(wanted)
            )
        )
        known_cases = set(result.scalars())
    for item in payload.items:
        scores = {
            s.name: {
                "value": s.value,
                "data_type": s.data_type,
                "comment": s.comment,
                "source": "sdk",
            }
            for s in item.scores
        }
        db.add(
            ExperimentItem(
                experiment_id=experiment.id,
                project_id=project.id,
                # Ignore ids from another project rather than failing the upload.
                dataset_item_id=item.dataset_item_id
                if item.dataset_item_id in known_cases
                else None,
                input=item.input,
                expected_output=item.expected_output,
                output=item.output,
                status="error" if item.error else "ok",
                error=item.error,
                trace_id=item.trace_id,
                latency_ms=item.latency_ms,
                scores=scores or None,
            )
        )
    await db.commit()
    return {"accepted": len(payload.items)}


@router.post("/v1/experiments/{experiment_id}/complete", response_model=ExperimentOut)
async def complete_experiment_v1(
    experiment_id: uuid.UUID,
    project: Project = Depends(get_write_project),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    """Signal that all results are uploaded. Evaluation runs in the background;
    poll `GET /v1/experiments/{id}` until `status` is `completed`."""
    experiment = await _load_v1(db, project, experiment_id)
    if experiment.status == "running":
        await _start(db, experiment)
    return await _out(db, experiment)


@router.get("/v1/experiments/{experiment_id}", response_model=ExperimentOut)
async def get_experiment_v1(
    experiment_id: uuid.UUID,
    project: Project = Depends(get_read_project),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    return await _out(db, await _load_v1(db, project, experiment_id))
