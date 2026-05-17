"""Workflow registry, version snapshots, and run ledger ORM models.

Phase 5 of the additive orchestration refactor — mirrors the
:mod:`aqp.persistence.models_agents` layout line-for-line so the new
hash-locked :class:`aqp.agents.orchestration.spec.WorkflowSpec` gets
the same ``*_spec_versions`` semantics every other AQP runtime has
(agents / bots / rl / analysis).

Three tables:

- :class:`WorkflowSpecRow` — logical workflow (latest active version).
- :class:`WorkflowSpecVersion` — immutable, hash-locked snapshot of a
  ``WorkflowSpec`` payload. Re-snapshotting a changed spec creates a
  NEW row; existing rows are append-only audit records (parallel to
  ``agent_spec_versions``).
- :class:`WorkflowRun` — one execution of a workflow by
  :class:`aqp.agents.orchestration.runtime.WorkflowRuntime`. Carries
  the ``experiment_id`` + ``test_id`` FK columns required by hard
  rule 34.

The migration that creates these tables is
:mod:`alembic.versions.0046_workflow_versioning`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class WorkflowSpecRow(Base, ProjectScopedMixin):
    """Logical workflow — the latest active version of a named spec."""

    __tablename__ = "workflow_specs"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(160), nullable=False, unique=True, index=True)
    adapter = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    annotations = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WorkflowSpecVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of a :class:`WorkflowSpec`."""

    __tablename__ = "workflow_spec_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("workflow_specs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    spec_hash = Column(String(64), nullable=False, unique=True, index=True)
    payload = Column(JSON, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index(
    "ix_workflow_spec_versions_spec_version",
    WorkflowSpecVersion.spec_id,
    WorkflowSpecVersion.version,
)


class WorkflowRun(Base, ProjectScopedMixin):
    """One execution of a workflow by :class:`WorkflowRuntime`.

    Hard rule 34: every new run-producing flow MUST carry
    ``experiment_id`` / ``test_id`` FKs. They are nullable so legacy
    invocations (no surrounding experiment) still persist a row.
    """

    __tablename__ = "workflow_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    workflow_spec_name = Column(String(160), nullable=False, index=True)
    spec_version_id = Column(
        String(36),
        ForeignKey("workflow_spec_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_run_id = Column(String(36), nullable=True, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    inputs = Column(JSON, default=dict)
    final_state = Column(JSON, default=dict)
    breadcrumbs = Column(JSON, default=list)
    cost_usd = Column(Float, nullable=False, default=0.0)
    n_calls = Column(Integer, nullable=False, default=0)
    n_tool_calls = Column(Integer, nullable=False, default=0)
    n_rag_hits = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Float, nullable=True)
    halted = Column(Boolean, nullable=False, default=False)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    # Rule 34 — every *_runs row gets these.
    experiment_id = Column(
        String(36),
        ForeignKey("experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_id = Column(
        String(36),
        ForeignKey("tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


Index("ix_workflow_runs_status_started", WorkflowRun.status, WorkflowRun.started_at)


__all__ = [
    "WorkflowRun",
    "WorkflowSpecRow",
    "WorkflowSpecVersion",
]
