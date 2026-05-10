"""Dagster sandbox session ledger (data fabric phase 3 — Alembic 0034)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DagsterSandboxSessionRow(Base, ProjectScopedMixin):
    """One ephemeral interactive Dagster sandbox session."""

    __tablename__ = "dagster_sandbox_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    status = Column(String(32), nullable=False, default="open", index=True)
    components_json = Column(JSON, default=dict)
    log_summary_json = Column(JSON, default=list)
    last_run_id = Column(String(64), nullable=True, index=True)
    folder = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index(
    "ix_dagster_sandbox_sessions_workspace_status",
    DagsterSandboxSessionRow.workspace_id,
    DagsterSandboxSessionRow.status,
)


__all__ = ["DagsterSandboxSessionRow"]
