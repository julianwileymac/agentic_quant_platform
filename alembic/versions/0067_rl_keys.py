"""Rate-limit keys table (Phase 0 — Foundations, plan section 4).

Revision ID: 0067_rl_keys
Revises: 0066_rl_policies
Create Date: 2026-05-24

Per-user vendor key bindings pointing at Vault paths that hold the
actual vendor secret. Rotating the underlying vendor secret never
touches this table — only the Vault path's value changes. The
``rl_keys`` row records ``(owner_user_id, service, label, vault_path,
policy_id, issued_at, expires_at, revoked_at)`` for audit + lifecycle.

RLS-protected by ``workspace_id`` per AGENTS rule 51.

Per AGENTS rule 6 (root): immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0067_rl_keys"
down_revision = "0066_rl_policies"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "rl_keys",
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
        sa.Column(
            "policy_id",
            sa.String(36),
            sa.ForeignKey("rl_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(120), nullable=False, server_default="primary"),
        sa.Column("vault_path", sa.String(500), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column(
            "revoked_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "owner_user_id",
            "service",
            "label",
            name="uq_rl_keys_owner_service_label",
        ),
    )
    op.create_index(
        "ix_rl_keys_owner_user_id", "rl_keys", ["owner_user_id"]
    )
    op.create_index(
        "ix_rl_keys_workspace_id", "rl_keys", ["workspace_id"]
    )
    op.create_index("ix_rl_keys_service", "rl_keys", ["service"])
    op.create_index(
        "ix_rl_keys_service_owner", "rl_keys", ["service", "owner_user_id"]
    )
    op.create_index("ix_rl_keys_revoked_at", "rl_keys", ["revoked_at"])

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE rl_keys ENABLE ROW LEVEL SECURITY;
                ALTER TABLE rl_keys FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_rl_keys ON rl_keys;
                CREATE POLICY tenant_isolation_rl_keys ON rl_keys
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE ON rl_keys TO app_runtime;
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
                    WHERE table_name = 'rl_keys'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_rl_keys ON rl_keys;
                    ALTER TABLE rl_keys NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE rl_keys DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_rl_keys_revoked_at", table_name="rl_keys")
    op.drop_index("ix_rl_keys_service_owner", table_name="rl_keys")
    op.drop_index("ix_rl_keys_service", table_name="rl_keys")
    op.drop_index("ix_rl_keys_workspace_id", table_name="rl_keys")
    op.drop_index("ix_rl_keys_owner_user_id", table_name="rl_keys")
    op.drop_table("rl_keys")
