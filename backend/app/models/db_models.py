import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Numeric(10, 5), default=0)
    latency_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2))


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[str | None] = mapped_column(Text)
    credibility_score: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    relevant_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float | None] = mapped_column(Float)
    agent: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(Text)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    numeric_unit: Mapped[str | None] = mapped_column(Text)
    time_period: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    # search_tsv is a DB-generated STORED column (see migration) — intentionally
    # not mapped here since the ORM must never write to it.


class FactCheckResult(Base):
    __tablename__ = "fact_check_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"))
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    verifying_source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Contradiction(Base):
    __tablename__ = "contradictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"))
    topic: Mapped[str | None] = mapped_column(Text)
    evidence_a_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id"))
    evidence_b_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id"))
    explanation: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False)


class Figure(Base):
    __tablename__ = "figures"
    __table_args__ = (CheckConstraint("cardinality(evidence_ids) > 0", name="figure_must_be_attributed"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    alt_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    spec: Mapped[dict | None] = mapped_column(JSONB)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"))
    license_note: Mapped[str | None] = mapped_column(Text)
    paired_figure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("figures.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"))
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False)
    figure_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NodeTrace(Base):
    __tablename__ = "node_traces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"))
    node_name: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    input: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    status: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_version: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    preferred_mode: Mapped[str | None] = mapped_column(Text)
    preferred_source_types: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    preferred_report_format: Mapped[str | None] = mapped_column(Text)
