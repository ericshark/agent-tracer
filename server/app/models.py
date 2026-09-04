import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSON that becomes JSONB on PostgreSQL and plain JSON elsewhere (tests on SQLite).
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampedUuidMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class User(TimestampedUuidMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    projects: Mapped[list["Project"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Project(TimestampedUuidMixin, Base):
    __tablename__ = "projects"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="projects")
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ApiKey(TimestampedUuidMixin, Base):
    __tablename__ = "api_keys"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # SHA-256 hex digest of the full key. The plaintext key is shown once at creation.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # First characters of the key ("at_1a2b3c…") so users can tell keys apart.
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="api_keys")


class ProviderCredential(TimestampedUuidMixin, Base):
    """Optional per-project model-provider API key used only by the replay engine.

    The key is encrypted at rest with a Fernet key derived from SECRET_KEY.
    """

    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("project_id", "provider", name="uq_provider_cred"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # anthropic | openai
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Trace(TimestampedUuidMixin, Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("project_id", "trace_id", name="uq_trace_per_project"),
        Index("ix_traces_project_started", "project_id", "started_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # W3C-style 32-char lowercase hex id supplied by the SDK / OTLP exporter.
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="trace")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONVariant)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Aggregates maintained at ingest time.
    span_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    spans: Mapped[list["Span"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan", passive_deletes=True
    )
    shares: Mapped[list["ShareLink"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds() * 1000.0


class Span(TimestampedUuidMixin, Base):
    __tablename__ = "spans"
    __table_args__ = (
        UniqueConstraint("trace_pk", "span_id", name="uq_span_per_trace"),
        Index("ix_spans_trace_started", "trace_pk", "started_at"),
    )

    trace_pk: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # W3C-style 16-char lowercase hex id.
    span_id: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(16))

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # AGENT | LLM | TOOL | CHAIN | RETRIEVER | EMBEDDING | GUARDRAIL | UNKNOWN
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    input: Mapped[dict | list | str | None] = mapped_column(JSONVariant)
    output: Mapped[dict | list | str | None] = mapped_column(JSONVariant)
    attributes: Mapped[dict | None] = mapped_column(JSONVariant)
    events: Mapped[list | None] = mapped_column(JSONVariant)

    model: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    cost_usd: Mapped[float | None] = mapped_column(Float)

    error_type: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_stacktrace: Mapped[str | None] = mapped_column(Text)

    trace: Mapped[Trace] = relationship(back_populates="spans")
    replays: Mapped[list["Replay"]] = relationship(
        back_populates="span", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds() * 1000.0


class ShareLink(TimestampedUuidMixin, Base):
    __tablename__ = "share_links"

    trace_pk: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trace: Mapped[Trace] = relationship(back_populates="shares")

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= utcnow():
            return False
        return True


class Replay(TimestampedUuidMixin, Base):
    """A safe re-execution of a single LLM span.

    Replays never mutate the original trace; each attempt is stored separately.
    """

    __tablename__ = "replays"

    span_pk: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # simulation | anthropic | openai
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONVariant)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    cost_usd: Mapped[float | None] = mapped_column(Float)

    span: Mapped[Span] = relationship(back_populates="replays")
