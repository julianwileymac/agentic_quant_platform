"""Rate-limit ledger (Phase 0 — Foundations, plan section 4).

Revision ID: 0068_rl_ledger
Revises: 0067_rl_keys
Create Date: 2026-05-24

Append-only audit + observability ledger. The Postgres path
partitions ``rl_ledger`` by RANGE on ``ts`` so quarterly partitions
can drop cleanly when retention windows expire. Non-Postgres
dialects (SQLite test fixtures) get a plain table.

RLS-protected by ``workspace_id`` per AGENTS rule 51. The ledger
table is in :data:`aqp.tenancy.rls_policies.RLS_TABLES` (see the
follow-up edit in the same Phase 0 PR).

Per AGENTS rule 6 (root): immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0068_rl_ledger"
down_revision = "0067_rl_keys"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "rl_ledger",
        sa.Column(
            "id",
            sa.BigInteger,
            primary_key=True,
            autoincrement=True,
        ),
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
        sa.Column(
            "ts",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("service", sa.String(120), nullable=False),
        sa.Column("key_id", sa.String(36), nullable=False),
        sa.Column(
            "tokens_consumed",
            sa.Integer,
            nullable=False,
            server_default="1",
        ),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("request_hash", sa.LargeBinary, nullable=True),
        sa.Column("asset_key", sa.String(500), nullable=True),
        sa.Column(
            "actor_kind",
            sa.String(16),
            nullable=False,
            server_default="user",
        ),
        sa.Column("agent_subject", sa.String(255), nullable=True),
        sa.Column(
            "on_behalf_of_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_rl_ledger_ts", "rl_ledger", ["ts"])
    op.create_index("ix_rl_ledger_service", "rl_ledger", ["service"])
    op.create_index("ix_rl_ledger_key_id", "rl_ledger", ["key_id"])
    op.create_index("ix_rl_ledger_decision", "rl_ledger", ["decision"])
    op.create_index(
        "ix_rl_ledger_ts_service", "rl_ledger", ["ts", "service"]
    )
    op.create_index(
        "ix_rl_ledger_owner_ts", "rl_ledger", ["owner_user_id", "ts"]
    )
    op.create_index(
        "ix_rl_ledger_workspace_id", "rl_ledger", ["workspace_id"]
    )

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE rl_ledger ENABLE ROW LEVEL SECURITY;
                ALTER TABLE rl_ledger FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_rl_ledger ON rl_ledger;
                CREATE POLICY tenant_isolation_rl_ledger ON rl_ledger
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE ON rl_ledger TO app_runtime;
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
                    WHERE table_name = 'rl_ledger'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_rl_ledger ON rl_ledger;
                    ALTER TABLE rl_ledger NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE rl_ledger DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_rl_ledger_workspace_id", table_name="rl_ledger")
    op.drop_index("ix_rl_ledger_owner_ts", table_name="rl_ledger")
    op.drop_index("ix_rl_ledger_ts_service", table_name="rl_ledger")
    op.drop_index("ix_rl_ledger_decision", table_name="rl_ledger")
    op.drop_index("ix_rl_ledger_key_id", table_name="rl_ledger")
    op.drop_index("ix_rl_ledger_service", table_name="rl_ledger")
    op.drop_index("ix_rl_ledger_ts", table_name="rl_ledger")
    op.drop_table("rl_ledger")
