"""Per-user external OAuth2 token registry (Workstream D).

Revision ID: 0062_user_oauth_tokens
Revises: 0061_lineage_signing_archive
Create Date: 2026-05-24

Creates ``user_oauth_tokens`` — one row per (user, source) external
OAuth2 connection. The model stores Vault path + metadata only; the
encrypted access/refresh-token blob lives at ``vault_path`` inside
the Vault Transit-backed store
(:mod:`aqp.credentials.vault_transit`).

AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0062_user_oauth_tokens"
down_revision = "0061_lineage_signing_archive"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "user_oauth_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("vault_path", sa.String(240), nullable=False),
        sa.Column("scopes", sa.JSON, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime, nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime, nullable=True),
        sa.Column("label", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.Column(
            "revoked_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_oauth_tokens_user_id",
        "user_oauth_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_user_oauth_tokens_org",
        "user_oauth_tokens",
        ["organization_id"],
    )
    op.create_index(
        "ix_user_oauth_tokens_source",
        "user_oauth_tokens",
        ["source"],
    )
    op.create_index(
        "ix_user_oauth_tokens_expires",
        "user_oauth_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_user_oauth_tokens_revoked",
        "user_oauth_tokens",
        ["revoked_at"],
    )
    op.create_index(
        "ix_user_oauth_tokens_user_source",
        "user_oauth_tokens",
        ["user_id", "source"],
    )
    # Partial unique on (user, source) where revoked_at IS NULL ->
    # PostgreSQL only. SQLite tests get the non-partial unique below.
    if _is_postgres():
        op.execute(
            "CREATE UNIQUE INDEX ix_user_oauth_tokens_active_unique "
            "ON user_oauth_tokens (user_id, source) WHERE revoked_at IS NULL"
        )
    else:
        op.create_index(
            "ix_user_oauth_tokens_active_unique",
            "user_oauth_tokens",
            ["user_id", "source"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index("ix_user_oauth_tokens_active_unique", table_name="user_oauth_tokens")
    op.drop_index("ix_user_oauth_tokens_user_source", table_name="user_oauth_tokens")
    op.drop_index("ix_user_oauth_tokens_revoked", table_name="user_oauth_tokens")
    op.drop_index("ix_user_oauth_tokens_expires", table_name="user_oauth_tokens")
    op.drop_index("ix_user_oauth_tokens_source", table_name="user_oauth_tokens")
    op.drop_index("ix_user_oauth_tokens_org", table_name="user_oauth_tokens")
    op.drop_index("ix_user_oauth_tokens_user_id", table_name="user_oauth_tokens")
    op.drop_table("user_oauth_tokens")
