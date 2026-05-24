"""Per-team Airbyte workspace (Phase 1 — Airbyte plane, plan section 5).

Revision ID: 0070_airbyte_workspace_per_team
Revises: 0069_user_tiers_template_catalog_audit
Create Date: 2026-05-24

Adds ``organizations.airbyte_workspace_id`` so each tenant gets its
own Airbyte workspace. Backfills with the default workspace id (NULL)
for existing rows; the Phase 1 controller provisions one per team
via the official Airbyte Terraform provider v1.2.1.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0070_airbyte_workspace_per_team"
down_revision = "0069_user_tiers_template_catalog_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "airbyte_workspace_id",
            sa.String(64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_organizations_airbyte_workspace_id",
        "organizations",
        ["airbyte_workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organizations_airbyte_workspace_id",
        table_name="organizations",
    )
    op.drop_column("organizations", "airbyte_workspace_id")
