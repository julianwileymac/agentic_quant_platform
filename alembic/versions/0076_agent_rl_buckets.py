"""Per-agent rate-limit buckets (Phase 4 — plan section 8).

Revision ID: 0076_agent_rl_buckets
Revises: 0075_ingestion_approvals
Create Date: 2026-05-24

Bounds the autonomous agents' independent vendor exploration
budget per AGENTS rule 54 — an agent cannot drain the user's
$500/mo Polygon budget by issuing thousands of preview_source
calls in one chain-of-thought. The :class:`PerAgentStrategy` in
``aqp_ratelimit`` reads this table to discover the per-agent
ceiling at runtime.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0076_agent_rl_buckets"
down_revision = "0075_ingestion_approvals"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "agent_rl_buckets",
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
        sa.Column("agent_sub", sa.String(255), nullable=False),
        sa.Column("service", sa.String(120), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False),
        sa.Column(
            "refill_rate",
            sa.Float,
            nullable=False,
            comment="Tokens per second",
        ),
        sa.Column("monthly_quota", sa.BigInteger, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "agent_sub",
            "service",
            "workspace_id",
            name="uq_agent_rl_buckets_agent_service",
        ),
    )
    op.create_index(
        "ix_agent_rl_buckets_agent_sub",
        "agent_rl_buckets",
        ["agent_sub"],
    )
    op.create_index(
        "ix_agent_rl_buckets_service",
        "agent_rl_buckets",
        ["service"],
    )
    op.create_index(
        "ix_agent_rl_buckets_workspace_id",
        "agent_rl_buckets",
        ["workspace_id"],
    )
    op.create_index(
        "ix_agent_rl_buckets_owner_user_id",
        "agent_rl_buckets",
        ["owner_user_id"],
    )

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE agent_rl_buckets ENABLE ROW LEVEL SECURITY;
                ALTER TABLE agent_rl_buckets FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_agent_rl_buckets
                    ON agent_rl_buckets;
                CREATE POLICY tenant_isolation_agent_rl_buckets
                    ON agent_rl_buckets
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON agent_rl_buckets TO app_runtime;
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
                    WHERE table_name = 'agent_rl_buckets'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_agent_rl_buckets
                        ON agent_rl_buckets;
                    ALTER TABLE agent_rl_buckets NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE agent_rl_buckets DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_agent_rl_buckets_owner_user_id", table_name="agent_rl_buckets")
    op.drop_index("ix_agent_rl_buckets_workspace_id", table_name="agent_rl_buckets")
    op.drop_index("ix_agent_rl_buckets_service", table_name="agent_rl_buckets")
    op.drop_index("ix_agent_rl_buckets_agent_sub", table_name="agent_rl_buckets")
    op.drop_table("agent_rl_buckets")
