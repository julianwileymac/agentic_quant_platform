"""Kernel session ORM (Phase 3, plan section 7).

One row per Jupyter Enterprise Gateway kernel pod. The Phase 6
janitor task reaps rows whose ``terminated_at`` is null but whose
matching Kubernetes pod no longer exists.

RLS-protected by ``workspace_id`` per AGENTS rule 51.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import TenantOwnedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class KernelSession(Base, TenantOwnedMixin):
    """One Jupyter Enterprise Gateway kernel pod the user owns."""

    __tablename__ = "kernel_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    kernel_id = Column(String(64), nullable=False, unique=True, index=True)
    image = Column(String(255), nullable=False)
    pod_name = Column(String(255), nullable=True, index=True)
    namespace = Column(String(120), nullable=True, index=True)
    resource_quota_ref = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = Column(DateTime, nullable=True)
    terminated_at = Column(DateTime, nullable=True, index=True)
    terminated_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    meta = Column(JSON, nullable=False, server_default="{}")

    __table_args__ = (
        UniqueConstraint("kernel_id", name="uq_kernel_sessions_kernel_id"),
        Index("ix_kernel_sessions_owner_started", "owner_user_id", "started_at"),
    )


__all__ = ["KernelSession"]
