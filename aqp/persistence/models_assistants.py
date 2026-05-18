"""Assistant Engine ORM models.

Phase 2 of the Assistant Engine refactor. Mirrors
:mod:`aqp.persistence.models_workflows` line-for-line so the new
hash-locked :class:`aqp.assistants.spec.AssistantSpec` gets the same
``*_spec_versions`` semantics every other AQP runtime has (agents /
bots / rl / analysis / workflows).

Tables:

- :class:`AssistantSpecRow` — logical assistant (latest active version).
- :class:`AssistantSpecVersion` — immutable, hash-locked snapshot.
- :class:`AssistantSession` — per-user conversation thread.
- :class:`AssistantMessage` — one user / assistant / tool message turn.
- :class:`AssistantRun` — one execution by :class:`AssistantRuntime`.
  Carries ``experiment_id`` / ``test_id`` / ``halt_token`` / nullable
  ``halted_at`` and links to the underlying ``agent_runs_v2.id`` or
  ``workflow_runs.id`` via ``target_run_kind`` + ``target_run_id``.
- :class:`AssistantRunEvent` — structured timeline rows the frontend
  uses to reconstruct execution.
- :class:`AssistantSkill` — markdown-skill descriptor cache (content
  hash + metadata; no autonomous mutation).

Migration: :mod:`alembic.versions.0054_assistant_engine`.
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


class AssistantSpecRow(Base, ProjectScopedMixin):
    """Logical assistant — the latest active version of a named spec."""

    __tablename__ = "assistant_specs"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(160), nullable=False, unique=True, index=True)
    mode = Column(String(16), nullable=False, default="agent")
    target_ref = Column(String(160), nullable=False, default="")
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    annotations = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AssistantSpecVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of an :class:`AssistantSpec`."""

    __tablename__ = "assistant_spec_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    spec_id = Column(
        String(36),
        ForeignKey("assistant_specs.id", ondelete="CASCADE"),
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
    "ix_assistant_spec_versions_spec_version",
    AssistantSpecVersion.spec_id,
    AssistantSpecVersion.version,
)


class AssistantSession(Base, ProjectScopedMixin):
    """One conversation thread between a user (or service) and an assistant."""

    __tablename__ = "assistant_sessions"
    id = Column(String(36), primary_key=True, default=_uuid)
    assistant_spec_name = Column(String(160), nullable=False, index=True)
    title = Column(String(240), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_active_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    extra = Column(JSON, default=dict)


Index(
    "ix_assistant_sessions_active",
    AssistantSession.assistant_spec_name,
    AssistantSession.last_active_at,
)


class AssistantMessage(Base, ProjectScopedMixin):
    """One user / assistant / tool message inside a session."""

    __tablename__ = "assistant_messages"
    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(36),
        ForeignKey("assistant_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(String(36), nullable=True, index=True)
    turn = Column(Integer, nullable=False)
    role = Column(String(32), nullable=False)  # user | assistant | tool | system
    content = Column(Text, nullable=False, default="")
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index(
    "ix_assistant_messages_session_turn",
    AssistantMessage.session_id,
    AssistantMessage.turn,
)


class AssistantRun(Base, ProjectScopedMixin):
    """One execution of an assistant by :class:`AssistantRuntime`.

    Hard rule 34: every run-producing flow carries
    ``experiment_id`` / ``test_id`` FKs (nullable so legacy invocations
    still persist a row). ``target_run_kind`` + ``target_run_id``
    point at the underlying ``agent_runs_v2.id`` or ``workflow_runs.id``
    so the frontend can deep-link from a single assistant run into the
    full agent / workflow trace.
    """

    __tablename__ = "assistant_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    assistant_spec_name = Column(String(160), nullable=False, index=True)
    spec_version_id = Column(
        String(36),
        ForeignKey("assistant_spec_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id = Column(
        String(36),
        ForeignKey("assistant_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id = Column(String(120), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    target_kind = Column(String(16), nullable=False, default="agent")
    target_ref = Column(String(160), nullable=False, default="")
    target_run_kind = Column(String(16), nullable=True)  # agent | workflow
    target_run_id = Column(String(36), nullable=True, index=True)
    inputs = Column(JSON, default=dict)
    output = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    cost_usd = Column(Float, nullable=False, default=0.0)
    n_calls = Column(Integer, nullable=False, default=0)
    n_tool_calls = Column(Integer, nullable=False, default=0)
    n_rag_hits = Column(Integer, nullable=False, default=0)
    halted = Column(Boolean, nullable=False, default=False)
    halt_token = Column(String(64), nullable=True)
    halted_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    # Rule 34 — experiment + test linkage.
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


Index(
    "ix_assistant_runs_status_started",
    AssistantRun.status,
    AssistantRun.started_at,
)


class AssistantRunEvent(Base, ProjectScopedMixin):
    """Structured timeline row used by the frontend ``ProgressTimeline``.

    Persisted alongside the canonical :func:`aqp.tasks._progress.emit`
    frame so a completed run can be reconstructed deterministically
    (turn number, span name, attributes, status, cost, duration).
    """

    __tablename__ = "assistant_run_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("assistant_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    kind = Column(String(48), nullable=False)
    name = Column(String(120), nullable=False)
    attributes = Column(JSON, default=dict)
    status = Column(String(32), nullable=True)
    cost_usd = Column(Float, nullable=True)
    duration_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index(
    "ix_assistant_run_events_run_seq",
    AssistantRunEvent.run_id,
    AssistantRunEvent.seq,
)


class AssistantSkill(Base, ProjectScopedMixin):
    """Cached descriptor for a Markdown-described assistant skill.

    Skills are read-only — the row exists so the UI can render skill
    catalogs without re-scanning the filesystem on every request.
    The ``content_hash`` lets the registry detect modifications.
    """

    __tablename__ = "assistant_skills"
    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(160), nullable=False, unique=True, index=True)
    title = Column(String(240), nullable=False, default="")
    content_hash = Column(String(64), nullable=False)
    path = Column(String(1024), nullable=False)
    tags = Column(JSON, default=list)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "AssistantMessage",
    "AssistantRun",
    "AssistantRunEvent",
    "AssistantSession",
    "AssistantSkill",
    "AssistantSpecRow",
    "AssistantSpecVersion",
]
