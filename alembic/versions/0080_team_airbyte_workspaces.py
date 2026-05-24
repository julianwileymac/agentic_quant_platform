"""Per-team Airbyte workspace mapping (Phase 6, plan section 10).

Revision ID: 0080_team_airbyte_workspaces
Revises: 0079_audit_log_hash_chain
Create Date: 2026-05-24

Alembic 0070 added ``organizations.airbyte_workspace_id``; Phase 6
adds the team-level workspace mapping so a single org can split
its ingestion plane across multiple workspaces (one per team,
matching the dbt-mesh structure).

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0080_team_airbyte_workspaces"
down_revision = "0079_audit_log_hash_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_airbyte_workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("airbyte_workspace_id", sa.String(64), nullable=False),
        sa.Column(
            "dagster_agent_label",
            sa.String(120),
            nullable=False,
            server_default="default",
        ),
        sa.Column(
            "monthly_budget_tokens",
            sa.BigInteger,
            nullable=True,
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
    )
    op.create_index(
        "ix_team_airbyte_workspaces_team_id",
        "team_airbyte_workspaces",
        ["team_id"],
    )
    op.create_index(
        "ix_team_airbyte_workspaces_organization_id",
        "team_airbyte_workspaces",
        ["organization_id"],
    )
    op.create_index(
        "ix_team_airbyte_workspaces_airbyte_workspace_id",
        "team_airbyte_workspaces",
        ["airbyte_workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_team_airbyte_workspaces_airbyte_workspace_id",
        table_name="team_airbyte_workspaces",
    )
    op.drop_index(
        "ix_team_airbyte_workspaces_organization_id",
        table_name="team_airbyte_workspaces",
    )
    op.drop_index(
        "ix_team_airbyte_workspaces_team_id",
        table_name="team_airbyte_workspaces",
    )
    op.drop_table("team_airbyte_workspaces")
