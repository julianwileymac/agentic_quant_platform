"""Analysis spec / version / run / step-result ORM models.

Mirrors :mod:`aqp.persistence.models_rl`:

- ``analysis_specs`` — logical analysis row, latest active version of a
  named spec inside a project.
- ``analysis_spec_versions`` — immutable, hash-locked snapshot of every
  :class:`aqp.analysis.spec.AnalysisSpec` the registry has ever seen.
- ``analysis_runs`` — one row per ``run`` / ``preview`` invocation of
  :class:`aqp.analysis.runtime.AnalysisRuntime`.
- ``analysis_step_results`` — one row per :class:`AnalysisStep` in the
  spec, joined to ``analysis_runs`` via ``run_id``.

Tenancy: every table mixes in :class:`ProjectScopedMixin` so workspace
/ project / owner-user columns drop in alongside the canonical
``aqp_gold_analysis_*`` Iceberg tenancy columns written by
:func:`aqp.data.iceberg_catalog._stamp_tenancy_columns`.
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


class AnalysisSpec(Base, ProjectScopedMixin):
    """Logical analysis spec — the latest active version of a named spec."""

    __tablename__ = "analysis_specs"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False)
    slug = Column(String(120), nullable=False, index=True)
    kind = Column(String(32), nullable=False, default="research", index=True)
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    spec_yaml = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    annotations = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "slug", name="uq_analysis_specs_project_slug"
        ),
    )


class AnalysisSpecVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of an :class:`AnalysisSpec`."""

    __tablename__ = "analysis_spec_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("analysis_specs.id", ondelete="CASCADE"),
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
        UniqueConstraint(
            "spec_id", "spec_hash", name="uq_analysis_versions_spec_hash"
        ),
        UniqueConstraint(
            "spec_id", "version", name="uq_analysis_versions_spec_version"
        ),
    )


Index(
    "ix_analysis_versions_spec_version",
    AnalysisSpecVersion.spec_id,
    AnalysisSpecVersion.version,
)


class AnalysisRun(Base, ProjectScopedMixin):
    """One execution of an :class:`AnalysisSpec` (run | preview)."""

    __tablename__ = "analysis_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("analysis_specs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version_id = Column(
        String(36),
        ForeignKey("analysis_spec_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target = Column(String(40), nullable=False, default="run", index=True)
    task_id = Column(String(120), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    dataset_descriptor = Column(String(400), nullable=True)
    dataset_hash = Column(String(64), nullable=True)
    mlflow_run_id = Column(String(120), nullable=True)
    iceberg_result_table = Column(String(240), nullable=True)
    result_summary = Column(JSON, default=dict)
    metrics = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)


Index("ix_analysis_runs_status_started", AnalysisRun.status, AnalysisRun.started_at)


class AnalysisStepResult(Base, ProjectScopedMixin):
    """One step's outcome inside an :class:`AnalysisRun`."""

    __tablename__ = "analysis_step_results"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_alias = Column(String(160), nullable=False, index=True)
    flow = Column(String(160), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="completed", index=True)
    params_json = Column(JSON, default=dict)
    metrics_json = Column(JSON, default=dict)
    artifact_uri = Column(String(400), nullable=True)
    duration_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "step_alias", name="uq_analysis_step_results_run_alias"
        ),
    )


__all__ = [
    "AnalysisRun",
    "AnalysisSpec",
    "AnalysisSpecVersion",
    "AnalysisStepResult",
]
