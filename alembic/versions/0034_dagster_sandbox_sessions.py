"""Dagster sandbox sessions ledger.

Revision ID: 0034_dagster_sandbox_sessions
Revises: 0033_airbyte_manifest_storage
Create Date: 2026-05-09

Phase 3 of the self-service data fabric expansion. Adds the
``dagster_sandbox_sessions`` table backing
:class:`aqp.dagster.sandbox.SandboxRuntime`. The runtime keeps the
authoritative in-memory state (folder + Redis namespace); this table
is the audit trail + janitor target.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0034_dagster_sandbox_sessions"
down_revision = "0033_airbyte_manifest_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dagster_sandbox_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("components_json", sa.JSON(), nullable=True),
        sa.Column("log_summary_json", sa.JSON(), nullable=True),
        sa.Column("last_run_id", sa.String(length=64), nullable=True),
        sa.Column("folder", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dagster_sandbox_sessions_status",
        "dagster_sandbox_sessions",
        ["status"],
    )
    op.create_index(
        "ix_dagster_sandbox_sessions_expires_at",
        "dagster_sandbox_sessions",
        ["expires_at"],
    )
    op.create_index(
        "ix_dagster_sandbox_sessions_last_run_id",
        "dagster_sandbox_sessions",
        ["last_run_id"],
    )
    op.create_index(
        "ix_dagster_sandbox_sessions_workspace_status",
        "dagster_sandbox_sessions",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dagster_sandbox_sessions_workspace_status",
        table_name="dagster_sandbox_sessions",
    )
    op.drop_index(
        "ix_dagster_sandbox_sessions_last_run_id",
        table_name="dagster_sandbox_sessions",
    )
    op.drop_index(
        "ix_dagster_sandbox_sessions_expires_at",
        table_name="dagster_sandbox_sessions",
    )
    op.drop_index(
        "ix_dagster_sandbox_sessions_status",
        table_name="dagster_sandbox_sessions",
    )
    op.drop_table("dagster_sandbox_sessions")
