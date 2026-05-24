"""Ingestion approvals table (Phase 4 — plan section 8).

Revision ID: 0075_ingestion_approvals
Revises: 0074_kernel_sessions
Create Date: 2026-05-24

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0075_ingestion_approvals"
down_revision = "0074_kernel_sessions"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "ingestion_approvals",
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
        sa.Column("requested_by_agent_sub", sa.String(255), nullable=False),
        sa.Column(
            "on_behalf_of_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_id", sa.String(120), nullable=False),
        sa.Column("args_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("estimated_cost_tokens", sa.String(64), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "decided_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.Column("decision_notes", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("applied_at", sa.DateTime, nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_ingestion_approvals_owner_user_id",
        "ingestion_approvals",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_ingestion_approvals_workspace_id",
        "ingestion_approvals",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ingestion_approvals_requested_by_agent_sub",
        "ingestion_approvals",
        ["requested_by_agent_sub"],
    )
    op.create_index(
        "ix_ingestion_approvals_on_behalf_of_user_id",
        "ingestion_approvals",
        ["on_behalf_of_user_id"],
    )
    op.create_index(
        "ix_ingestion_approvals_tool_id",
        "ingestion_approvals",
        ["tool_id"],
    )
    op.create_index(
        "ix_ingestion_approvals_status",
        "ingestion_approvals",
        ["status"],
    )
    op.create_index(
        "ix_ingestion_approvals_status_expires",
        "ingestion_approvals",
        ["status", "expires_at"],
    )

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE ingestion_approvals ENABLE ROW LEVEL SECURITY;
                ALTER TABLE ingestion_approvals FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_ingestion_approvals
                    ON ingestion_approvals;
                CREATE POLICY tenant_isolation_ingestion_approvals
                    ON ingestion_approvals
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON ingestion_approvals TO app_runtime;
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
                    WHERE table_name = 'ingestion_approvals'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_ingestion_approvals
                        ON ingestion_approvals;
                    ALTER TABLE ingestion_approvals NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE ingestion_approvals DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index(
        "ix_ingestion_approvals_status_expires",
        table_name="ingestion_approvals",
    )
    op.drop_index("ix_ingestion_approvals_status", table_name="ingestion_approvals")
    op.drop_index("ix_ingestion_approvals_tool_id", table_name="ingestion_approvals")
    op.drop_index(
        "ix_ingestion_approvals_on_behalf_of_user_id",
        table_name="ingestion_approvals",
    )
    op.drop_index(
        "ix_ingestion_approvals_requested_by_agent_sub",
        table_name="ingestion_approvals",
    )
    op.drop_index("ix_ingestion_approvals_workspace_id", table_name="ingestion_approvals")
    op.drop_index("ix_ingestion_approvals_owner_user_id", table_name="ingestion_approvals")
    op.drop_table("ingestion_approvals")
