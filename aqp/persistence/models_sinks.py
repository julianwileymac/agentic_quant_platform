"""Sink registry ORM models.

Backs the ``/sinks`` API and the ``Sinks`` UI page. A :class:`SinkRow`
is a logical, project-scoped sink configuration that can be plugged
into any :class:`aqp.data.engine.PipelineManifest` as the terminal
node. :class:`SinkVersionRow` is an immutable, hash-locked snapshot
written every time the configuration changes (mirroring the
``bot_versions`` and ``agent_spec_versions`` patterns).

A :class:`SinkRow` does **not** own any IO logic — runtime sinks live
under :mod:`aqp.data.fetchers.sinks`. The row simply persists the
``NodeSpec`` arguments (``kind`` + ``config``) so the catalog can be
attached to a manifest, versioned, and project-scoped.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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


class SinkRow(Base, ProjectScopedMixin):
    """Logical sink — the latest active version of a named sink in a project."""

    __tablename__ = "sinks"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(180), nullable=False, index=True)
    kind = Column(String(64), nullable=False, default="iceberg", index=True)
    display_name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    config_json = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    documentation_url = Column(String(1024), nullable=True)
    requires_manifest_node = Column(Boolean, nullable=False, default=True)
    current_version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    annotations = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_sinks_project_name"),
    )


class SinkVersionRow(Base, ProjectScopedMixin):
    """Immutable, hash-locked snapshot of a :class:`SinkRow` configuration."""

    __tablename__ = "sink_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    sink_id = Column(
        String(36),
        ForeignKey("sinks.id", ondelete="CASCADE"),
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
        UniqueConstraint("sink_id", "spec_hash", name="uq_sink_versions_hash"),
        UniqueConstraint("sink_id", "version", name="uq_sink_versions_version"),
    )


Index("ix_sink_versions_sink_version", SinkVersionRow.sink_id, SinkVersionRow.version)


__all__ = ["SinkRow", "SinkVersionRow"]
