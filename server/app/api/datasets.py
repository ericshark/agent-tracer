import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import can_access, load_trace
from app.api.deps import (
    get_current_user,
    get_owned_project,
    get_read_project,
    get_write_project,
)
from app.core.datasets import (
    DatasetError,
    add_items,
    export_jsonl,
    item_counts,
    item_from_span,
    parse_import,
    root_span,
)
from app.db import get_db
from app.models import Dataset, DatasetItem, Project, User, utcnow
from app.schemas.datasets import (
    DatasetCreate,
    DatasetImport,
    DatasetItemList,
    DatasetItemOut,
    DatasetItemsCreate,
    DatasetItemUpdate,
    DatasetOut,
    DatasetUpdate,
    DatasetWithItems,
    ItemsFromTraces,
)

router = APIRouter(tags=["datasets"])


async def load_dataset(db: AsyncSession, user: User, dataset_id: uuid.UUID) -> Dataset:
    result = await db.execute(
        select(Dataset)
        .join(Project, Dataset.project_id == Project.id)
        .where(Dataset.id == dataset_id, can_access(user))
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    return dataset


async def get_owned_dataset(
    dataset_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dataset:
    return await load_dataset(db, user, dataset_id)


async def _out(db: AsyncSession, dataset: Dataset) -> DatasetOut:
    out = DatasetOut.model_validate(dataset)
    out.item_count = (await item_counts(db, [dataset.id])).get(dataset.id, 0)
    return out


async def _create(db: AsyncSession, project: Project, payload: DatasetCreate) -> Dataset:
    existing = await db.execute(
        select(Dataset.id).where(Dataset.project_id == project.id, Dataset.name == payload.name)
    )
    if existing.first() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A dataset named {payload.name!r} already exists"
        )
    dataset = Dataset(project_id=project.id, name=payload.name, description=payload.description)
    db.add(dataset)
    await db.flush()
    return dataset


# ------------------------------------------------------------------- dashboard


@router.get("/api/projects/{project_id}/datasets", response_model=list[DatasetOut])
async def list_datasets(
    project: Project = Depends(get_owned_project), db: AsyncSession = Depends(get_db)
) -> list[DatasetOut]:
    result = await db.execute(
        select(Dataset).where(Dataset.project_id == project.id).order_by(Dataset.created_at)
    )
    datasets = list(result.scalars())
    counts = await item_counts(db, [d.id for d in datasets])
    out = []
    for dataset in datasets:
        item = DatasetOut.model_validate(dataset)
        item.item_count = counts.get(dataset.id, 0)
        out.append(item)
    return out


@router.post(
    "/api/projects/{project_id}/datasets",
    response_model=DatasetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(
    payload: DatasetCreate,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> DatasetOut:
    dataset = await _create(db, project, payload)
    await db.commit()
    return DatasetOut.model_validate(dataset)


@router.get("/api/datasets/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset: Dataset = Depends(get_owned_dataset), db: AsyncSession = Depends(get_db)
) -> DatasetOut:
    return await _out(db, dataset)


@router.patch("/api/datasets/{dataset_id}", response_model=DatasetOut)
async def update_dataset(
    payload: DatasetUpdate,
    dataset: Dataset = Depends(get_owned_dataset),
    db: AsyncSession = Depends(get_db),
) -> DatasetOut:
    if payload.name is not None and payload.name != dataset.name:
        clash = await db.execute(
            select(Dataset.id).where(
                Dataset.project_id == dataset.project_id, Dataset.name == payload.name
            )
        )
        if clash.first() is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A dataset named {payload.name!r} already exists"
            )
        dataset.name = payload.name
    if payload.description is not None:
        dataset.description = payload.description
    await db.commit()
    return await _out(db, dataset)


@router.delete("/api/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset: Dataset = Depends(get_owned_dataset), db: AsyncSession = Depends(get_db)
) -> None:
    await db.delete(dataset)
    await db.commit()


@router.get("/api/datasets/{dataset_id}/items", response_model=DatasetItemList)
async def list_items(
    dataset: Dataset = Depends(get_owned_dataset),
    db: AsyncSession = Depends(get_db),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> DatasetItemList:
    query = select(DatasetItem).where(DatasetItem.dataset_id == dataset.id)
    if not include_archived:
        query = query.where(DatasetItem.archived_at.is_(None))
    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    result = await db.execute(
        query.order_by(DatasetItem.created_at, DatasetItem.id).limit(limit).offset(offset)
    )
    return DatasetItemList(
        items=[DatasetItemOut.model_validate(i) for i in result.scalars()],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/datasets/{dataset_id}/items",
    response_model=list[DatasetItemOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_items(
    payload: DatasetItemsCreate,
    dataset: Dataset = Depends(get_owned_dataset),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetItemOut]:
    rows = add_items(db, dataset, payload.items)
    await db.commit()
    return [DatasetItemOut.model_validate(r) for r in rows]


@router.post(
    "/api/datasets/{dataset_id}/items/from-traces",
    response_model=list[DatasetItemOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_items_from_traces(
    payload: ItemsFromTraces,
    dataset: Dataset = Depends(get_owned_dataset),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetItemOut]:
    rows = []
    for source in payload.sources:
        trace = await load_trace(db, user, source.trace_pk)
        if trace.project_id != dataset.project_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Trace belongs to a different project"
            )
        if source.span_pk is None:
            span = root_span(trace)
        else:
            span = next((s for s in trace.spans if s.id == source.span_pk), None)
        if span is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Span not found")
        row = item_from_span(dataset, trace, span)
        db.add(row)
        rows.append(row)
    await db.commit()
    return [DatasetItemOut.model_validate(r) for r in rows]


@router.post(
    "/api/datasets/{dataset_id}/import",
    response_model=list[DatasetItemOut],
    status_code=status.HTTP_201_CREATED,
)
async def import_items(
    payload: DatasetImport,
    dataset: Dataset = Depends(get_owned_dataset),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetItemOut]:
    """Import JSONL (one object per line) or CSV (header row required).

    Records with an `input` key use `input` / `expected_output` / `metadata`;
    anything else becomes the input as a whole.
    """
    try:
        items = parse_import(payload.format, payload.content)
    except DatasetError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = add_items(db, dataset, items)
    await db.commit()
    return [DatasetItemOut.model_validate(r) for r in rows]


@router.get("/api/datasets/{dataset_id}/export", response_class=PlainTextResponse)
async def export_items(
    dataset: Dataset = Depends(get_owned_dataset), db: AsyncSession = Depends(get_db)
) -> PlainTextResponse:
    result = await db.execute(
        select(DatasetItem)
        .where(DatasetItem.dataset_id == dataset.id, DatasetItem.archived_at.is_(None))
        .order_by(DatasetItem.created_at, DatasetItem.id)
    )
    return PlainTextResponse(
        export_jsonl(list(result.scalars())), media_type="application/x-ndjson"
    )


async def _load_item(db: AsyncSession, user: User, item_id: uuid.UUID) -> DatasetItem:
    result = await db.execute(
        select(DatasetItem)
        .join(Project, DatasetItem.project_id == Project.id)
        .where(DatasetItem.id == item_id, can_access(user))
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset item not found")
    return item


@router.patch("/api/dataset-items/{item_id}", response_model=DatasetItemOut)
async def update_item(
    item_id: uuid.UUID,
    payload: DatasetItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DatasetItemOut:
    item = await _load_item(db, user, item_id)
    # Only fields present in the request are changed, so `null` can clear a value.
    sent = payload.model_fields_set
    if "input" in sent:
        item.input = payload.input
    if "expected_output" in sent:
        item.expected_output = payload.expected_output
    if "metadata" in sent:
        item.meta = payload.metadata
    if payload.archived is not None:
        item.archived_at = utcnow() if payload.archived else None
    await db.commit()
    await db.refresh(item)
    return DatasetItemOut.model_validate(item)


@router.delete("/api/dataset-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    item = await _load_item(db, user, item_id)
    await db.delete(item)
    await db.commit()


# ------------------------------------------------------------- SDK-facing (/v1)


async def _by_name(db: AsyncSession, project: Project, name: str) -> Dataset:
    result = await db.execute(
        select(Dataset).where(Dataset.project_id == project.id, Dataset.name == name)
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Dataset {name!r} not found")
    return dataset


@router.get("/v1/datasets", response_model=list[DatasetOut])
async def list_datasets_v1(
    project: Project = Depends(get_read_project), db: AsyncSession = Depends(get_db)
) -> list[DatasetOut]:
    return await list_datasets(project=project, db=db)


@router.post("/v1/datasets", response_model=DatasetOut)
async def create_dataset_v1(
    payload: DatasetCreate,
    project: Project = Depends(get_write_project),
    db: AsyncSession = Depends(get_db),
) -> DatasetOut:
    """Create a dataset, or return the existing one with that name."""
    result = await db.execute(
        select(Dataset).where(Dataset.project_id == project.id, Dataset.name == payload.name)
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        dataset = await _create(db, project, payload)
        await db.commit()
    return await _out(db, dataset)


@router.get("/v1/datasets/{name}", response_model=DatasetWithItems)
async def get_dataset_v1(
    name: str,
    project: Project = Depends(get_read_project),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> DatasetWithItems:
    dataset = await _by_name(db, project, name)
    listing = await list_items(
        dataset=dataset, db=db, include_archived=False, limit=limit, offset=offset
    )
    # Built field by field: validating from the ORM object would lazy-load `items`.
    return DatasetWithItems(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        created_at=dataset.created_at,
        item_count=listing.total,
        items=listing.items,
    )


@router.post(
    "/v1/datasets/{name}/items",
    response_model=list[DatasetItemOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_items_v1(
    name: str,
    payload: DatasetItemsCreate,
    project: Project = Depends(get_write_project),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetItemOut]:
    dataset = await _by_name(db, project, name)
    rows = add_items(db, dataset, payload.items)
    await db.commit()
    return [DatasetItemOut.model_validate(r) for r in rows]
