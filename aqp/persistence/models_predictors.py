"""Phase 5 persistence: PredictorSpecVersionRow + PricingContextRun.

Reflects the schema added in Alembic migration ``0044_pricing_context_runs``.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence.models import Base, _uuid


class PredictorSpecVersionRow(Base):
    """Hash-locked snapshot of a :class:`PredictorSpec`.

    Mirrors the ``agent_spec_versions`` / ``bot_versions`` /
    ``rl_experiment_versions`` / ``analysis_spec_versions`` pattern:
    every hash change inserts a new row, never an in-place mutation.
    """

    __tablename__ = "predictor_spec_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    predictor_name = Column(String(120), nullable=False, index=True)
    spec_hash = Column(String(64), nullable=False)
    spec_body = Column(JSON, nullable=False)
    model_kind = Column(String(32), nullable=False, index=True)
    target_horizon = Column(String(32), nullable=False, index=True)
    label_kind = Column(String(24), nullable=False, index=True)
    feature_columns = Column(JSON, default=list)
    hyperparams_json = Column(JSON, default=dict)
    description = Column(Text, nullable=True)
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "predictor_name",
            "spec_hash",
            name="uq_predictor_spec_versions_name_hash",
        ),
    )


class PricingContextRunRow(Base):
    """One row per :class:`PricingContext` execution.

    Used by the Phase 5 ``data.pricing.*`` MCP tools for audit /
    explanation. Carries the active context state, the measure
    requested, the elapsed time, and the resulting value (small) or
    Iceberg identifier (large).
    """

    __tablename__ = "pricing_context_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    context_id = Column(String(64), nullable=False, index=True)
    measure = Column(String(64), nullable=False, index=True)
    instrument_class = Column(String(120), nullable=True, index=True)
    instrument_ref = Column(String(240), nullable=True)
    as_of = Column(DateTime, nullable=True)
    market_data_source = Column(String(120), nullable=True)
    behaviour = Column(String(32), nullable=True)
    dispatch = Column(String(16), nullable=False)
    status = Column(String(24), nullable=False, default="running", index=True)
    value_scalar = Column(Float, nullable=True)
    value_json = Column(JSON, default=dict)
    arrow_identifier = Column(String(240), nullable=True)
    elapsed_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id = Column(String(64), nullable=True)
    ts_started = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    ts_completed = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)


__all__ = [
    "PredictorSpecVersionRow",
    "PricingContextRunRow",
]
