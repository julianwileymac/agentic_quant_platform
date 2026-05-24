"""Connector marketplace seed expansion + extra metadata (Phase 5).

Revision ID: 0077_connector_marketplace_extras
Revises: 0076_agent_rl_buckets
Create Date: 2026-05-24

Phase 5 seeds 50+ templates into ``template_catalog`` (Alembic 0069
created the table). This migration adds optional metadata columns
that Phase 5 templates use:

- ``preview_supported`` — whether ``data.ingest.preview_source``
  is wired for this template.
- ``cost_per_sync_hint`` — operator-visible token-cost hint shown
  in the Create-Connection Wizard.
- ``output_schema_url`` — optional pointer to a schema document
  the Vite UI renders alongside the form.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0077_connector_marketplace_extras"
down_revision = "0076_agent_rl_buckets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "template_catalog",
        sa.Column(
            "preview_supported",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "template_catalog",
        sa.Column("cost_per_sync_hint", sa.Integer, nullable=True),
    )
    op.add_column(
        "template_catalog",
        sa.Column("output_schema_url", sa.String(500), nullable=True),
    )
    op.create_index(
        "ix_template_catalog_preview_supported",
        "template_catalog",
        ["preview_supported"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_template_catalog_preview_supported",
        table_name="template_catalog",
    )
    op.drop_column("template_catalog", "output_schema_url")
    op.drop_column("template_catalog", "cost_per_sync_hint")
    op.drop_column("template_catalog", "preview_supported")
