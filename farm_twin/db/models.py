"""SQLAlchemy 2 mappings for persistence; observation, estimate and prediction remain separate."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Date,
    BigInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PropertyORM(Base):
    __tablename__ = "property"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(Text)
    country_iso: Mapped[str] = mapped_column(String(2), nullable=False)
    region_code: Mapped[str | None] = mapped_column(Text)
    tz: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Kolkata")
    ref_point: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    local_epsg: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    land_unit_factors: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class PlotORM(Base):
    __tablename__ = "plot"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    property_id: Mapped[UUID] = mapped_column(ForeignKey("property.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326), nullable=False)
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    eligible_uses: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    land_use: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("property_id", "name"),)


class VariableDefORM(Base):
    __tablename__ = "variable_def"
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str | None] = mapped_column(Text)
    canonical_unit: Mapped[str] = mapped_column(Text, nullable=False)
    min_valid: Mapped[float | None] = mapped_column(Float)
    max_valid: Mapped[float | None] = mapped_column(Float)
    domain: Mapped[str | None] = mapped_column(Text)


class DatasetORM(Base):
    __tablename__ = "dataset"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    kind: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    uri: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spatial_extent: Mapped[Any | None] = mapped_column(Geometry("POLYGON", srid=4326))
    time_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ScenarioORM(Base):
    __tablename__ = "scenario"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    property_id: Mapped[UUID] = mapped_column(ForeignKey("property.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ApiIdempotencyORM(Base):
    __tablename__ = "api_idempotency"
    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AsyncJobORM(Base):
    __tablename__ = "async_job"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="QUEUED")
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "idempotency_key"),)


class ObservationORM(Base):
    __tablename__ = "observation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    plot_id: Mapped[UUID | None] = mapped_column(ForeignKey("plot.id"))
    property_id: Mapped[UUID | None] = mapped_column(ForeignKey("property.id"))
    variable: Mapped[str] = mapped_column(ForeignKey("variable_def.code"), nullable=False)
    depth_top_m: Mapped[float | None] = mapped_column(Float)
    depth_bottom_m: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(Text)
    dataset_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    uncertainty_sd: Mapped[float | None] = mapped_column(Float)
    quality_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    superseded_by: Mapped[UUID | None] = mapped_column(ForeignKey("observation.id"))
    __table_args__ = (
        UniqueConstraint("plot_id", "variable", "depth_top_m", "depth_bottom_m", "observed_at", "dataset_id"),
    )


class EstimateORM(Base):
    __tablename__ = "estimate"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    plot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    variable: Mapped[str] = mapped_column(Text, nullable=False)
    depth_top_m: Mapped[float | None] = mapped_column(Float)
    depth_bottom_m: Mapped[float | None] = mapped_column(Float)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    uncertainty_sd: Mapped[float] = mapped_column(Float, nullable=False)
    parent_ids: Mapped[list] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False)


class PredictionORM(Base):
    __tablename__ = "prediction"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    sim_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    variable: Mapped[str] = mapped_column(Text, nullable=False)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    depth_top_m: Mapped[float | None] = mapped_column(Float)
    depth_bottom_m: Mapped[float | None] = mapped_column(Float)
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    sd: Mapped[float | None] = mapped_column(Float)
    q05: Mapped[float | None] = mapped_column(Float)
    q50: Mapped[float | None] = mapped_column(Float)
    q95: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(Text, nullable=False)


class ParameterSetORM(Base):
    __tablename__ = "parameter_set"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    parent_set_id: Mapped[UUID | None] = mapped_column(ForeignKey("parameter_set.id"))
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    posterior: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_report_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class SimRunORM(Base):
    __tablename__ = "sim_run"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    scenario_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rng_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parameter_set_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    code_git_sha: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class StateDeltaORM(Base):
    __tablename__ = "state_delta"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    sim_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("sim_run.id"))
    state_date: Mapped[date | None] = mapped_column(Date)
    parent_state_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    delta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_snapshot: Mapped[bool | None] = mapped_column(server_default=text("false"))


class InterventionORM(Base):
    __tablename__ = "intervention"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    plot_id: Mapped[UUID | None] = mapped_column(ForeignKey("plot.id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    proposed_by: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_id: Mapped[UUID | None] = mapped_column(ForeignKey("recommendation.id"))
    approval_id: Mapped[UUID | None] = mapped_column(ForeignKey("approval.id"))
    planned_date: Mapped[date | None] = mapped_column(Date)
    executed_date: Mapped[date | None] = mapped_column(Date)
    actual_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class CalibrationRunORM(Base):
    __tablename__ = "calibration_run"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    model: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(Text)
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    method: Mapped[str | None] = mapped_column(Text)
    data_window: Mapped[Any | None] = mapped_column(TSTZRANGE)
    n_obs: Mapped[int | None] = mapped_column(Integer)
    train_idx: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    holdout_idx: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metrics_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metrics_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decision: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    candidate_set_id: Mapped[UUID | None] = mapped_column(ForeignKey("parameter_set.id"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class AgentRunORM(Base):
    __tablename__ = "agent_run"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    thread_id: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_request: Mapped[str | None] = mapped_column(Text)
    graph_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)


class ToolCallORM(Base):
    __tablename__ = "tool_call"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    agent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_run.id"))
    agent: Mapped[str | None] = mapped_column(Text)
    tool: Mapped[str | None] = mapped_column(Text)
    args: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result_hash: Mapped[str | None] = mapped_column(Text)
    ok: Mapped[bool | None] = mapped_column()
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    approval_id: Mapped[UUID | None] = mapped_column(ForeignKey("approval.id"))


class AuditLogORM(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    actor: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    entity: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


def make_engine(database_url: str, **kwargs: Any):
    from sqlalchemy import create_engine

    return create_engine(database_url, pool_pre_ping=True, **kwargs)


class OutboxORM(Base):
    __tablename__ = "event_outbox"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    plot_id: Mapped[UUID | None] = mapped_column(ForeignKey("plot.id", ondelete="SET NULL"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecommendationORM(Base):
    __tablename__ = "recommendation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    scenario_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    sim_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evidence_refs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)


class ApprovalORM(Base):
    __tablename__ = "approval"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    recommendation_id: Mapped[UUID] = mapped_column(ForeignKey("recommendation.id"), nullable=False)
    decided_by: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    token_hash: Mapped[str | None] = mapped_column(Text)


class OutcomeORM(Base):
    __tablename__ = "outcome"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    intervention_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    variable: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    prediction_id: Mapped[UUID | None] = mapped_column(ForeignKey("prediction.id"))
    error: Mapped[float | None] = mapped_column(Float)
