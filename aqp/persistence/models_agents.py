"""Agent registry, runs, evaluations, and annotation ORM models.

These tables back :class:`aqp.agents.spec.AgentSpec` (declarative) and
:class:`aqp.agents.runtime.AgentRuntime` (execution + telemetry). They
sit alongside the existing ``agent_runs`` / ``crew_runs`` tables — the
new ``agent_runs_v2`` is the spec-driven runtime; the old ``agent_runs``
remains for the legacy CrewAI research crew.
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

from aqp.persistence._tenancy_mixins import LabScopedMixin, ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AgentSpecRow(Base, ProjectScopedMixin):
    """Logical agent — the latest active version of a named spec."""

    __tablename__ = "agent_specs"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(120), nullable=False, unique=True, index=True)
    role = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AgentSpecVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of an :class:`AgentSpec`."""

    __tablename__ = "agent_spec_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("agent_specs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    spec_hash = Column(String(64), nullable=False, unique=True, index=True)
    payload = Column(JSON, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("ix_agent_spec_versions_spec_version", AgentSpecVersion.spec_id, AgentSpecVersion.version)


class AgentRunV2(Base, ProjectScopedMixin):
    """One execution of a spec via :class:`AgentRuntime`."""

    __tablename__ = "agent_runs_v2"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_name = Column(String(120), nullable=False, index=True)
    spec_version_id = Column(
        String(36),
        ForeignKey("agent_spec_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id = Column(String(120), nullable=True, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    inputs = Column(JSON, default=dict)
    output = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    cost_usd = Column(Float, nullable=False, default=0.0)
    n_calls = Column(Integer, nullable=False, default=0)
    n_tool_calls = Column(Integer, nullable=False, default=0)
    n_rag_hits = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class AgentRunStep(Base, ProjectScopedMixin):
    """One step inside a v2 run (tool call / LLM call / RAG retrieval / memory op)."""

    __tablename__ = "agent_run_steps"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("agent_runs_v2.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    kind = Column(String(40), nullable=False, index=True)  # llm | tool | rag | memory | guardrail | output
    name = Column(String(120), nullable=False)
    inputs = Column(JSON, default=dict)
    output = Column(JSON, default=dict)
    cost_usd = Column(Float, nullable=False, default=0.0)
    duration_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("ix_agent_run_steps_run_seq", AgentRunStep.run_id, AgentRunStep.seq)


class AgentRunArtifact(Base, ProjectScopedMixin):
    """Sidecar artifact (file / large blob) referenced by a run/step."""

    __tablename__ = "agent_run_artifacts"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("agent_runs_v2.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id = Column(
        String(36),
        ForeignKey("agent_run_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind = Column(String(60), nullable=False)  # prompt | response | csv | parquet | image | json
    name = Column(String(240), nullable=False)
    uri = Column(String(1024), nullable=False)
    bytes = Column(Integer, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AgentEvaluation(Base, ProjectScopedMixin):
    """One evaluation harness execution (golden replay, judge, eval set)."""

    __tablename__ = "agent_evaluations"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_name = Column(String(120), nullable=False, index=True)
    spec_version_id = Column(String(36), nullable=True, index=True)
    eval_set_name = Column(String(240), nullable=False)
    n_cases = Column(Integer, nullable=False, default=0)
    n_passed = Column(Integer, nullable=False, default=0)
    aggregate = Column(JSON, default=dict)
    notes = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class AgentEvalMetric(Base, ProjectScopedMixin):
    """One metric row inside an :class:`AgentEvaluation`."""

    __tablename__ = "agent_eval_metrics"
    id = Column(String(36), primary_key=True, default=_uuid)
    evaluation_id = Column(
        String(36),
        ForeignKey("agent_evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id = Column(String(120), nullable=False)
    metric = Column(String(80), nullable=False, index=True)
    value = Column(Float, nullable=True)
    text_value = Column(Text, nullable=True)
    passed = Column(Boolean, nullable=True)
    meta = Column(JSON, default=dict)


class AgentAnnotation(Base, LabScopedMixin):
    """User / agent annotation persisted for reproducibility / optimisation."""

    __tablename__ = "agent_annotations"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_name = Column(String(120), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    vt_symbol = Column(String(64), nullable=True, index=True)
    as_of = Column(DateTime, nullable=True, index=True)
    label = Column(String(120), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    payload = Column(JSON, default=dict)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "AgentAnnotation",
    "AgentEvalMetric",
    "AgentEvaluation",
    "AgentRunArtifact",
    "AgentRunStep",
    "AgentRunV2",
    "AgentSpecRow",
    "AgentSpecVersion",
]
