"""ORM model for ``mcp_tool_versions`` (Phase 5 §8.4).

Append-only catalog snapshots indexed by ``(tool_name, descriptor_hash)``.
Every MCP server writes here on boot; replay verifies the active
catalog matches the run's recorded hash set.

The companion table is ``agent_runs_v2`` which gained a
``mcp_tool_descriptor_hashes`` JSON column in Alembic
:mod:`alembic.versions.0084_mcp_tool_versioning`. The
``AgentRuntime`` writes that list when it persists the run.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MCPToolVersion(Base):
    """Append-only descriptor snapshot.

    Re-snapshotting an unchanged tool is a no-op (`INSERT ... ON
    CONFLICT DO NOTHING` against the unique constraint).
    """

    __tablename__ = "mcp_tool_versions"
    __table_args__ = (
        UniqueConstraint(
            "tool_name",
            "descriptor_hash",
            name="uq_mcp_tool_versions_name_hash",
        ),
        CheckConstraint(
            "length(descriptor_hash) = 64",
            name="ck_mcp_tool_versions_hash_sha256_hex",
        ),
    )

    id: str = Column(String(36), primary_key=True, default=_uuid)
    tool_name: str = Column(String(120), nullable=False, index=True)
    descriptor_hash: str = Column(String(64), nullable=False, index=True)
    descriptor_json = Column(JSON, nullable=False, default=dict)
    cell_id: str | None = Column(
        String(120),
        ForeignKey("cells.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: datetime = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    created_by: str | None = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


__all__ = ["MCPToolVersion"]
