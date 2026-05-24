"""Ed25519 signing-key archive for the lineage layer (Workstream C).

Revision ID: 0061_lineage_signing_archive
Revises: 0060_openlineage_outbox
Create Date: 2026-05-24

Adds the ``lineage_signing_key_archive`` table that pairs with
:mod:`aqp.auth.signing_keys`. Every Ed25519 key minted for a lineage
actor — service, agent, or user — has its public half archived here
so a historical signature on a ``lineage_transform_vertex`` row stays
verifiable after the active key has rotated.

The signature + signing_key_id columns themselves live on
``lineage_transform_vertex`` (created by 0059) and are populated by
:func:`aqp.auth.signing.sign_transform_payload`. This migration only
adds the archive lookup table.

AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0061_lineage_signing_archive"
down_revision = "0060_openlineage_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lineage_signing_key_archive",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key_id", sa.String(96), nullable=False, unique=True),
        sa.Column("public_key_pem", sa.Text, nullable=False),
        sa.Column("actor_kind", sa.String(32), nullable=False),
        sa.Column("actor_ref", sa.String(128), nullable=False),
        sa.Column("meta_json", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_lineage_signing_key_archive_key_id",
        "lineage_signing_key_archive",
        ["key_id"],
        unique=True,
    )
    op.create_index(
        "ix_lineage_signing_key_archive_actor_kind",
        "lineage_signing_key_archive",
        ["actor_kind"],
    )
    op.create_index(
        "ix_lineage_signing_key_archive_actor",
        "lineage_signing_key_archive",
        ["actor_kind", "actor_ref"],
    )
    op.create_index(
        "ix_lineage_signing_key_archive_created",
        "lineage_signing_key_archive",
        ["created_at"],
    )


def downgrade() -> None:
    for ix in (
        "ix_lineage_signing_key_archive_created",
        "ix_lineage_signing_key_archive_actor",
        "ix_lineage_signing_key_archive_actor_kind",
        "ix_lineage_signing_key_archive_key_id",
    ):
        op.drop_index(ix, table_name="lineage_signing_key_archive")
    op.drop_table("lineage_signing_key_archive")
