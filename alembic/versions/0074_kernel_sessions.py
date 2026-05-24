"""Kernel sessions table (Phase 3 — Hybrid DX, plan section 7).

Revision ID: 0074_kernel_sessions
Revises: 0073_dbt_mesh_projects
Create Date: 2026-05-24

One row per Jupyter Enterprise Gateway kernel pod the user owns.
Workspace-scoped + RLS-protected per AGENTS rule 51.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0074_kernel_sessions"
down_revision = "0073_dbt_mesh_projects"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "kernel_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kernel_id", sa.String(64), nullable=False, unique=True),
        sa.Column("image", sa.String(255), nullable=False),
        sa.Column("pod_name", sa.String(255), nullable=True),
        sa.Column("namespace", sa.String(120), nullable=True),
        sa.Column("resource_quota_ref", sa.Text, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
        sa.Column("terminated_at", sa.DateTime, nullable=True),
        sa.Column(
            "terminated_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_kernel_sessions_owner_user_id",
        "kernel_sessions",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_kernel_sessions_workspace_id",
        "kernel_sessions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_kernel_sessions_kernel_id",
        "kernel_sessions",
        ["kernel_id"],
    )
    op.create_index(
        "ix_kernel_sessions_pod_name",
        "kernel_sessions",
        ["pod_name"],
    )
    op.create_index(
        "ix_kernel_sessions_namespace",
        "kernel_sessions",
        ["namespace"],
    )
    op.create_index(
        "ix_kernel_sessions_started_at",
        "kernel_sessions",
        ["started_at"],
    )
    op.create_index(
        "ix_kernel_sessions_terminated_at",
        "kernel_sessions",
        ["terminated_at"],
    )
    op.create_index(
        "ix_kernel_sessions_owner_started",
        "kernel_sessions",
        ["owner_user_id", "started_at"],
    )

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE kernel_sessions ENABLE ROW LEVEL SECURITY;
                ALTER TABLE kernel_sessions FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_kernel_sessions ON kernel_sessions;
                CREATE POLICY tenant_isolation_kernel_sessions ON kernel_sessions
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE ON kernel_sessions TO app_runtime;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    if _is_postgres():
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'kernel_sessions'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_kernel_sessions ON kernel_sessions;
                    ALTER TABLE kernel_sessions NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE kernel_sessions DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_kernel_sessions_owner_started", table_name="kernel_sessions")
    op.drop_index("ix_kernel_sessions_terminated_at", table_name="kernel_sessions")
    op.drop_index("ix_kernel_sessions_started_at", table_name="kernel_sessions")
    op.drop_index("ix_kernel_sessions_namespace", table_name="kernel_sessions")
    op.drop_index("ix_kernel_sessions_pod_name", table_name="kernel_sessions")
    op.drop_index("ix_kernel_sessions_kernel_id", table_name="kernel_sessions")
    op.drop_index("ix_kernel_sessions_workspace_id", table_name="kernel_sessions")
    op.drop_index("ix_kernel_sessions_owner_user_id", table_name="kernel_sessions")
    op.drop_table("kernel_sessions")
