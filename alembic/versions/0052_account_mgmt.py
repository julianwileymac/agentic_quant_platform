"""Add security audit + tenancy invite tables; downgrade drops their indexes then tables to roll back account-management persistence changes cleanly."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0052_account_mgmt"
down_revision = "0051_seed_wiley_tech"
branch_labels = None
depends_on = None

_JSON_COMPAT = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_category", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("connection", sa.String(length=120), nullable=True),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("details", _JSON_COMPAT, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_security_audit_events_user_created_at_desc",
        "security_audit_events",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_security_audit_events_org_created_at_desc",
        "security_audit_events",
        ["organization_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_security_audit_events_event_type_created_at_desc",
        "security_audit_events",
        ["event_type", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_security_audit_events_created_at_desc",
        "security_audit_events",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_security_audit_events_actor_created_at_desc",
        "security_audit_events",
        ["actor_user_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "tenancy_invites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("team_id", sa.String(length=36), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("invited_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=8), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "uq_tenancy_invites_org_email_pending",
        "tenancy_invites",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_tenancy_invites_org_status_created_at_desc",
        "tenancy_invites",
        ["organization_id", "status", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_tenancy_invites_email_status",
        "tenancy_invites",
        ["email", "status"],
    )
    op.create_index(
        "uq_tenancy_invites_token_hash",
        "tenancy_invites",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_tenancy_invites_expires_at_pending",
        "tenancy_invites",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_tenancy_invites_expires_at_pending", table_name="tenancy_invites")
    op.drop_index("uq_tenancy_invites_token_hash", table_name="tenancy_invites")
    op.drop_index("ix_tenancy_invites_email_status", table_name="tenancy_invites")
    op.drop_index(
        "ix_tenancy_invites_org_status_created_at_desc",
        table_name="tenancy_invites",
    )
    op.drop_index("uq_tenancy_invites_org_email_pending", table_name="tenancy_invites")
    op.drop_table("tenancy_invites")

    op.drop_index(
        "ix_security_audit_events_actor_created_at_desc",
        table_name="security_audit_events",
    )
    op.drop_index(
        "ix_security_audit_events_created_at_desc",
        table_name="security_audit_events",
    )
    op.drop_index(
        "ix_security_audit_events_event_type_created_at_desc",
        table_name="security_audit_events",
    )
    op.drop_index(
        "ix_security_audit_events_org_created_at_desc",
        table_name="security_audit_events",
    )
    op.drop_index(
        "ix_security_audit_events_user_created_at_desc",
        table_name="security_audit_events",
    )
    op.drop_table("security_audit_events")
