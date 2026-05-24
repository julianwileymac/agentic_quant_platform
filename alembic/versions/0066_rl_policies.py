"""Rate-limit policies table (Phase 0 — Foundations, plan section 4).

Revision ID: 0066_rl_policies
Revises: 0065_broker_credentials_b2b
Create Date: 2026-05-24

First of four Phase 0 migrations introducing the per-(user, service,
key_id) rate-limit accounting subsystem. This migration creates the
``rl_policies`` table — declarative capacity / refill_rate keyed by
``(service, tier)``. The Lua bucket script reads these values via the
Redis policy cache that Celery beat refreshes every 60s.

The table is workspace-scoped + RLS-protected by ``workspace_id`` per
AGENTS rule 51; ``aqp.tenancy.rls_policies.RLS_TABLES`` adds the row.

Per AGENTS rule 6 (root): immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0066_rl_policies"
down_revision = "0065_broker_credentials_b2b"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "rl_policies",
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
        sa.Column("service", sa.String(120), nullable=False),
        sa.Column("tier", sa.String(32), nullable=False, server_default="free"),
        sa.Column("capacity", sa.Integer, nullable=False),
        sa.Column(
            "refill_rate",
            sa.Float,
            nullable=False,
            comment="Tokens per second",
        ),
        sa.Column(
            "refill_interval_ms",
            sa.Integer,
            nullable=False,
            server_default="1000",
        ),
        sa.Column(
            "window_ms",
            sa.Integer,
            nullable=False,
            server_default="60000",
        ),
        sa.Column("notes", sa.Text, nullable=True),
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
            "service", "tier", "workspace_id", name="uq_rl_policies"
        ),
    )
    op.create_index(
        "ix_rl_policies_owner_user_id", "rl_policies", ["owner_user_id"]
    )
    op.create_index(
        "ix_rl_policies_workspace_id", "rl_policies", ["workspace_id"]
    )
    op.create_index("ix_rl_policies_service", "rl_policies", ["service"])
    op.create_index("ix_rl_policies_tier", "rl_policies", ["tier"])
    op.create_index(
        "ix_rl_policies_service_active",
        "rl_policies",
        ["service", "is_active"],
    )

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE rl_policies ENABLE ROW LEVEL SECURITY;
                ALTER TABLE rl_policies FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_rl_policies ON rl_policies;
                CREATE POLICY tenant_isolation_rl_policies ON rl_policies
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE ON rl_policies TO app_runtime;
            ELSE
                RAISE NOTICE 'skipping rl_policies RLS — app_runtime role missing';
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
                    WHERE table_name = 'rl_policies'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_rl_policies ON rl_policies;
                    ALTER TABLE rl_policies NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE rl_policies DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_rl_policies_service_active", table_name="rl_policies")
    op.drop_index("ix_rl_policies_tier", table_name="rl_policies")
    op.drop_index("ix_rl_policies_service", table_name="rl_policies")
    op.drop_index("ix_rl_policies_workspace_id", table_name="rl_policies")
    op.drop_index("ix_rl_policies_owner_user_id", table_name="rl_policies")
    op.drop_table("rl_policies")
