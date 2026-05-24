"""Ingestion-approval ORM (Phase 4, plan section 8).

When an autonomous agent (root AGENTS.md rule 54) invokes a
mutating ``data.ingest.*`` or ``data.transform.*`` MCP tool, the
tool returns ``{"status": "pending_approval", "approval_id": ...}``
and writes a row here. The on-behalf-of user approves or rejects
through the Vite UI within the 24-hour TTL; once approved, a
Celery task materializes the tool's actual side effect.

Workspace-scoped + RLS-protected per AGENTS rule 51.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import TenantOwnedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _default_expires_at() -> datetime:
    return datetime.utcnow() + timedelta(hours=24)


STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"


class IngestionApproval(Base, TenantOwnedMixin):
    """A pending mutating-tool invocation awaiting human approval."""

    __tablename__ = "ingestion_approvals"

    id = Column(String(36), primary_key=True, default=_uuid)
    requested_by_agent_sub = Column(String(255), nullable=False, index=True)
    on_behalf_of_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tool_id = Column(String(120), nullable=False, index=True)
    args_json = Column(JSON, nullable=False, server_default="{}")
    estimated_cost_tokens = Column(String(64), nullable=True)
    status = Column(
        String(16),
        nullable=False,
        server_default=STATUS_PENDING,
        index=True,
    )
    decided_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at = Column(DateTime, nullable=True)
    decision_notes = Column(Text, nullable=True)
    expires_at = Column(
        DateTime,
        nullable=False,
        default=_default_expires_at,
    )
    applied_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_ingestion_approvals_status_expires",
            "status",
            "expires_at",
        ),
    )


__all__ = [
    "STATUS_APPLIED",
    "STATUS_APPROVED",
    "STATUS_EXPIRED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "IngestionApproval",
]
