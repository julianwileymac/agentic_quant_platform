"""Bot registry, versions, and deployment ORM models.

Backs :class:`aqp.bots.spec.BotSpec` (declarative) and
:class:`aqp.bots.runtime.BotRuntime` (execution + telemetry):

- ``bots`` — logical bot row (the latest active version of a named spec
  inside a project).
- ``bot_versions`` — immutable, hash-locked snapshot of every BotSpec
  the registry has ever seen for a given bot.
- ``bot_deployments`` — one row per deploy / backtest / paper / chat
  invocation; references the version that produced it so a run can be
  replayed against the exact spec it was built from.

All three tables are ``ProjectScopedMixin`` so the multi-tenant
ownership refactor (Alembic 0017–0019) covers them automatically.
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
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Bot(Base, ProjectScopedMixin):
    """Logical bot — the latest active version of a named spec inside a project."""

    __tablename__ = "bots"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False)
    slug = Column(String(120), nullable=False, index=True)
    kind = Column(String(32), nullable=False, default="trading", index=True)
    description = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    spec_yaml = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    annotations = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_bots_project_slug"),
    )


class BotVersion(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of a :class:`Bot`'s spec."""

    __tablename__ = "bot_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    bot_id = Column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
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
        UniqueConstraint("bot_id", "spec_hash", name="uq_bot_versions_bot_hash"),
        UniqueConstraint("bot_id", "version", name="uq_bot_versions_bot_version"),
    )


Index("ix_bot_versions_bot_version", BotVersion.bot_id, BotVersion.version)


class BotDeployment(Base, ProjectScopedMixin):
    """One execution of a bot — backtest, paper session, chat, or k8s deploy."""

    __tablename__ = "bot_deployments"
    id = Column(String(36), primary_key=True, default=_uuid)
    bot_id = Column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    version_id = Column(
        String(36),
        ForeignKey("bot_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target = Column(String(40), nullable=False, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    manifest_yaml = Column(Text, nullable=True)
    result_summary = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)


Index("ix_bot_deployments_status_started", BotDeployment.status, BotDeployment.started_at)


__all__ = [
    "Bot",
    "BotDeployment",
    "BotVersion",
]
