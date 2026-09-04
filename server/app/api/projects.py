import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_project
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_api_key,
    mask_secret,
)
from app.db import get_db
from app.models import ApiKey, Project, ProviderCredential, User, utcnow
from app.schemas.projects import (
    ApiKeyCreate,
    ApiKeyCreatedOut,
    ApiKeyOut,
    CredentialOut,
    CredentialPut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ProjectOut]:
    result = await db.execute(
        select(Project).where(Project.owner_id == user.id).order_by(Project.created_at)
    )
    return [ProjectOut.model_validate(p) for p in result.scalars()]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = Project(owner_id=user.id, name=payload.name, description=payload.description)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project: Project = Depends(get_owned_project)) -> ProjectOut:
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    payload: ProjectUpdate,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    await db.commit()
    await db.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project: Project = Depends(get_owned_project), db: AsyncSession = Depends(get_db)
) -> None:
    await db.delete(project)
    await db.commit()


# ---------------------------------------------------------------- API keys


@router.get("/{project_id}/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    project: Project = Depends(get_owned_project), db: AsyncSession = Depends(get_db)
) -> list[ApiKeyOut]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.project_id == project.id).order_by(ApiKey.created_at)
    )
    return [ApiKeyOut.model_validate(k) for k in result.scalars()]


@router.post(
    "/{project_id}/api-keys",
    response_model=ApiKeyCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: ApiKeyCreate,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedOut:
    plaintext, key_hash, prefix = generate_api_key()
    api_key = ApiKey(
        project_id=project.id, name=payload.name, key_hash=key_hash, key_prefix=prefix
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    out = ApiKeyOut.model_validate(api_key)
    return ApiKeyCreatedOut(**out.model_dump(), key=plaintext)


@router.delete("/{project_id}/api-keys/{key_id}", response_model=ApiKeyOut)
async def revoke_api_key(
    key_id: uuid.UUID,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyOut:
    api_key = await db.get(ApiKey, key_id)
    if api_key is None or api_key.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = utcnow()
        await db.commit()
        await db.refresh(api_key)
    return ApiKeyOut.model_validate(api_key)


# ------------------------------------------------- replay provider credentials


@router.get("/{project_id}/credentials", response_model=list[CredentialOut])
async def list_credentials(
    project: Project = Depends(get_owned_project), db: AsyncSession = Depends(get_db)
) -> list[CredentialOut]:
    result = await db.execute(
        select(ProviderCredential).where(ProviderCredential.project_id == project.id)
    )
    out = []
    for cred in result.scalars():
        plaintext = decrypt_secret(cred.encrypted_key) or ""
        out.append(
            CredentialOut(
                provider=cred.provider,
                masked_key=mask_secret(plaintext),
                base_url=cred.base_url,
                updated_at=cred.updated_at,
            )
        )
    return out


@router.put("/{project_id}/credentials", response_model=CredentialOut)
async def put_credential(
    payload: CredentialPut,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> CredentialOut:
    result = await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.project_id == project.id,
            ProviderCredential.provider == payload.provider,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        cred = ProviderCredential(project_id=project.id, provider=payload.provider)
        db.add(cred)
    cred.encrypted_key = encrypt_secret(payload.api_key)
    cred.base_url = payload.base_url
    await db.commit()
    await db.refresh(cred)
    return CredentialOut(
        provider=cred.provider,
        masked_key=mask_secret(payload.api_key),
        base_url=cred.base_url,
        updated_at=cred.updated_at,
    )


@router.delete("/{project_id}/credentials/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    provider: str,
    project: Project = Depends(get_owned_project),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.project_id == project.id,
            ProviderCredential.provider == provider,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credential not found")
    await db.delete(cred)
    await db.commit()
