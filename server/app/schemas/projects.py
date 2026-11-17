import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


ApiKeyScope = Literal["ingest", "read", "write"]


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Omitted → full access (ingest + read + write).
    scopes: list[ApiKeyScope] | None = Field(default=None, min_length=1)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    scopes: list[str] | None = None


class ApiKeyCreatedOut(ApiKeyOut):
    """Returned only once, immediately after creation — includes the plaintext key."""

    key: str


class CredentialPut(BaseModel):
    provider: str = Field(pattern="^(anthropic|openai)$")
    api_key: str = Field(min_length=8, max_length=512)
    base_url: str | None = Field(default=None, max_length=512)


class CredentialOut(BaseModel):
    provider: str
    masked_key: str
    base_url: str | None
    updated_at: datetime


class ModelPricePut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_prefix: str = Field(min_length=1, max_length=128)
    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)
    cache_read_per_mtok: float | None = Field(default=None, ge=0)
    cache_write_per_mtok: float | None = Field(default=None, ge=0)


class ModelPriceOut(ModelPricePut):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
