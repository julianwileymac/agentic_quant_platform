"""Replay-cache catalog (Phase 6 — Hardening, plan section 10).

Revision ID: 0078_replay_cache_entries
Revises: 0077_connector_marketplace_extras
Create Date: 2026-05-24

Catalogues every cassette stored in the
:class:`aqp_ratelimit.replay_cache.S3CassetteStore` so the Vite
UI can browse + pin them. Pinning a cassette extends the TTL
indefinitely — used for regulatory backtests whose reproducibility
must survive vendor schema changes.

Workspace-scoped + RLS-protected per AGENTS rule 51.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0078_replay_cache_entries"
down_revision = "0077_connector_marketplace_extras"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "replay_cache_entries",
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
        sa.Column("request_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("vendor_service", sa.String(120), nullable=False),
        sa.Column("user_id_scope", sa.String(36), nullable=True),
        sa.Column("s3_object_uri", sa.String(500), nullable=False),
        sa.Column(
            "cassette_meta_json",
            sa.JSON,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "cached_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ttl_until", sa.DateTime, nullable=True),
        sa.Column("pinned_until", sa.DateTime, nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
    )
    op.create_index(
        "ix_replay_cache_entries_request_hash",
        "replay_cache_entries",
        ["request_hash"],
    )
    op.create_index(
        "ix_replay_cache_entries_vendor_service",
        "replay_cache_entries",
        ["vendor_service"],
    )
    op.create_index(
        "ix_replay_cache_entries_owner_user_id",
        "replay_cache_entries",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_replay_cache_entries_workspace_id",
        "replay_cache_entries",
        ["workspace_id"],
    )
    op.create_index(
        "ix_replay_cache_entries_ttl_until",
        "replay_cache_entries",
        ["ttl_until"],
    )
    op.create_index(
        "ix_replay_cache_entries_pinned_until",
        "replay_cache_entries",
        ["pinned_until"],
    )

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE replay_cache_entries ENABLE ROW LEVEL SECURITY;
                ALTER TABLE replay_cache_entries FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_replay_cache_entries
                    ON replay_cache_entries;
                CREATE POLICY tenant_isolation_replay_cache_entries
                    ON replay_cache_entries
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON replay_cache_entries TO app_runtime;
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
                    WHERE table_name = 'replay_cache_entries'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_replay_cache_entries
                        ON replay_cache_entries;
                    ALTER TABLE replay_cache_entries NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE replay_cache_entries DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_replay_cache_entries_pinned_until", table_name="replay_cache_entries")
    op.drop_index("ix_replay_cache_entries_ttl_until", table_name="replay_cache_entries")
    op.drop_index("ix_replay_cache_entries_workspace_id", table_name="replay_cache_entries")
    op.drop_index("ix_replay_cache_entries_owner_user_id", table_name="replay_cache_entries")
    op.drop_index("ix_replay_cache_entries_vendor_service", table_name="replay_cache_entries")
    op.drop_index("ix_replay_cache_entries_request_hash", table_name="replay_cache_entries")
    op.drop_table("replay_cache_entries")
