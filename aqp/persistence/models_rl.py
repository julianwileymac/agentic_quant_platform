"""RL experiment / version / run / evaluation / trajectory-ref ORM models.

Mirrors :mod:`aqp.persistence.models_bots`:

- ``rl_experiment_specs`` — logical RL experiment row (the latest active
  version of a named spec inside a project).
- ``rl_experiment_versions`` — immutable, hash-locked snapshot of every
  :class:`aqp.rl.spec.RLExperimentSpec` the registry has ever seen.
- ``rl_runs`` — one row per train / evaluate / paper / replay /
  walk-forward invocation of :class:`aqp.rl.runtime.RLRuntime`.
- ``rl_evaluations`` — rollout summary tied to a run (separate from the
  episode-level ``rl_episodes`` rows).
- ``rl_trajectory_refs`` — pointers to row ranges in the Iceberg
  ``rl.trajectories`` table (one row per episode).
- ``rl_equity_curve_refs`` — pointers to ``rl.equity_curves`` rows.
- ``rl_component_registrations`` — DB-mirror of the in-memory RL
  component registry so the UI library browser doesn't have to import
  every Python module to enumerate options.

The existing :class:`aqp.persistence.models.RLEpisode` table gains a
``run_id`` FK to ``rl_runs.id`` via the same migration that creates
these tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RLExperimentSpec(Base, ProjectScopedMixin):
    """Logical RL experiment — the latest active version of a named spec."""

    __tablename__ = "rl_experiment_specs"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False)
    slug = Column(String(120), nullable=False, index=True)
    kind = Column(String(32), nullable=False, default="training", index=True)
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    spec_yaml = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    annotations = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_rl_experiment_specs_project_slug"),
    )


class RLExperimentVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of an :class:`RLExperimentSpec`."""

    __tablename__ = "rl_experiment_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("rl_experiment_specs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    spec_hash = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("spec_id", "spec_hash", name="uq_rl_versions_spec_hash"),
        UniqueConstraint("spec_id", "version", name="uq_rl_versions_spec_version"),
    )


Index(
    "ix_rl_versions_spec_version",
    RLExperimentVersion.spec_id,
    RLExperimentVersion.version,
)


class RLRun(Base, ProjectScopedMixin):
    """One execution of an :class:`RLExperimentSpec` — train / evaluate / paper / replay."""

    __tablename__ = "rl_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("rl_experiment_specs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version_id = Column(
        String(36),
        ForeignKey("rl_experiment_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target = Column(String(40), nullable=False, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    mlflow_run_id = Column(String(120), nullable=True)
    checkpoint = Column(String(1024), nullable=True)
    mean_reward = Column(Float, nullable=True)
    total_reward = Column(Float, nullable=True)
    sharpe = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    final_value = Column(Float, nullable=True)
    total_return = Column(Float, nullable=True)
    result_summary = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    # AGENTS.md hard rule 34: every run-producing flow MUST stamp
    # ``experiment_id``. Alembic migration ``0037_experiment_test_linkage``
    # already added the column + FK to ``aqp_experiments`` (ondelete
    # SET NULL); this ORM mirror lets :class:`RLRuntime._stamp_tenancy`
    # copy ``RequestContext.experiment_id`` onto new rows without
    # falling off the SQLAlchemy session.
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


Index("ix_rl_runs_status_started", RLRun.status, RLRun.started_at)


class RLEvaluation(Base, ProjectScopedMixin):
    """Rollout summary for an evaluate / paper / replay run."""

    __tablename__ = "rl_evaluations"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("rl_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    episodes = Column(Integer, nullable=False, default=1)
    deterministic = Column(Integer, nullable=False, default=1)
    mean_reward = Column(Float, nullable=True)
    sharpe = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    final_value = Column(Float, nullable=True)
    total_return = Column(Float, nullable=True)
    metrics = Column(JSON, default=dict)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class RLTrajectoryRef(Base, ProjectScopedMixin):
    """Pointer to the Iceberg ``rl.trajectories`` rows for one episode.

    Records the namespace + table + row range so the UI can fetch
    trajectories from DuckDB without scanning the whole table.
    """

    __tablename__ = "rl_trajectory_refs"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("rl_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    episode = Column(Integer, nullable=False, index=True)
    iceberg_namespace = Column(String(120), nullable=False, default="rl")
    iceberg_table = Column(String(120), nullable=False, default="trajectories")
    row_count = Column(Integer, nullable=False, default=0)
    first_step = Column(Integer, nullable=True)
    last_step = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RLEquityCurveRef(Base, ProjectScopedMixin):
    """Pointer to the Iceberg ``rl.equity_curves`` rows for one episode."""

    __tablename__ = "rl_equity_curve_refs"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("rl_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    episode = Column(Integer, nullable=False, index=True)
    iceberg_namespace = Column(String(120), nullable=False, default="rl")
    iceberg_table = Column(String(120), nullable=False, default="equity_curves")
    row_count = Column(Integer, nullable=False, default=0)
    initial_value = Column(Float, nullable=True)
    final_value = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RLComponentRegistration(Base, ProjectScopedMixin):
    """DB-mirror of an entry in the in-memory RL component registry.

    Refreshed on app startup so the UI ``/rl/components`` browser doesn't
    need to import every module to discover registered envs / rewards /
    observations / actions / policies / agents / data pipelines /
    ensemblers / experiments / trajectory_stores.
    """

    __tablename__ = "rl_component_registrations"
    id = Column(String(36), primary_key=True, default=_uuid)
    rl_kind = Column(String(40), nullable=False, index=True)
    alias = Column(String(160), nullable=False, index=True)
    module_path = Column(String(400), nullable=False)
    class_name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    source = Column(String(80), nullable=True, index=True)
    category = Column(String(120), nullable=True, index=True)
    schema = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("rl_kind", "alias", name="uq_rl_components_kind_alias"),
    )


__all__ = [
    "RLComponentRegistration",
    "RLEquityCurveRef",
    "RLEvaluation",
    "RLExperimentSpec",
    "RLExperimentVersion",
    "RLRun",
    "RLTrajectoryRef",
]
