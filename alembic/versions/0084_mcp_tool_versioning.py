"""MCP tool descriptor versioning + agent-run hash recording.

Revision ID: 0084_mcp_tool_versioning
Revises: 0083_audit_cell_id_column
Create Date: 2026-05-25

Phase 5 §8.4 (RESTRUCTURING_PLAN.md). Two related changes:

1. ``mcp_tool_versions`` — append-only catalog snapshots indexed by
   ``(tool_name, descriptor_hash)``. Every MCP server writes a row
   here on boot; ``ON CONFLICT DO NOTHING`` makes the boot-time
   catalog snapshot idempotent. A descriptor change → new hash → new
   row, never an update in place. Mirrors the spec-versioning
   pattern from Rules 13/15/17/24/41.

2. ``agent_runs_v2.mcp_tool_descriptor_hashes`` — JSON column
   recording the set of tool hashes the agent run actually saw. The
   replay harness (Phase 7 §10.2) verifies the same set is presently
   registered (or runs against the snapshot from
   ``mcp_tool_versions``).

Per AGENTS rule 6 this migration is immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0084_mcp_tool_versioning"
down_revision = "0083_audit_cell_id_column"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, name: str) -> bool:
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    try:
        return any(c["name"] == column for c in insp.get_columns(table))
    except Exception:  # pragma: no cover - defensive
        return False


def upgrade() -> None:
    op.create_table(
        "mcp_tool_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column(
            "descriptor_hash",
            sa.String(64),  # SHA-256 hex digest length
            nullable=False,
        ),
        sa.Column(
            "descriptor_json",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "cell_id",
            sa.String(120),
            sa.ForeignKey("cells.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # `(tool_name, descriptor_hash)` is the natural key — re-running
        # the boot snapshot is a no-op until a descriptor changes.
        sa.UniqueConstraint(
            "tool_name",
            "descriptor_hash",
            name="uq_mcp_tool_versions_name_hash",
        ),
    )
    op.create_index(
        "ix_mcp_tool_versions_tool_name", "mcp_tool_versions", ["tool_name"]
    )
    op.create_index(
        "ix_mcp_tool_versions_descriptor_hash",
        "mcp_tool_versions",
        ["descriptor_hash"],
    )
    op.create_index(
        "ix_mcp_tool_versions_cell_id", "mcp_tool_versions", ["cell_id"]
    )

    # ------------------------------------------------------------------
    # agent_runs_v2.mcp_tool_descriptor_hashes — JSON list of the
    # ``descriptor_hash`` values seen during the run. Optional; existing
    # rows have NULL.
    # ------------------------------------------------------------------
    bind = op.get_bind()
    if _table_exists(bind, "agent_runs_v2") and not _column_exists(
        bind, "agent_runs_v2", "mcp_tool_descriptor_hashes"
    ):
        op.add_column(
            "agent_runs_v2",
            sa.Column(
                "mcp_tool_descriptor_hashes",
                sa.JSON,
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "agent_runs_v2") and _column_exists(
        bind, "agent_runs_v2", "mcp_tool_descriptor_hashes"
    ):
        op.drop_column("agent_runs_v2", "mcp_tool_descriptor_hashes")

    op.drop_index(
        "ix_mcp_tool_versions_cell_id", table_name="mcp_tool_versions"
    )
    op.drop_index(
        "ix_mcp_tool_versions_descriptor_hash", table_name="mcp_tool_versions"
    )
    op.drop_index(
        "ix_mcp_tool_versions_tool_name", table_name="mcp_tool_versions"
    )
    op.drop_table("mcp_tool_versions")
