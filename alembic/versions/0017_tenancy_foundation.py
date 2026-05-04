"""Tenancy foundation: organizations, teams, users, workspaces, projects, labs,
memberships, config overlays + deterministic default seed.

Revision ID: 0017_tenancy_foundation
Revises: 0016_extraction_metadata
Create Date: 2026-05-03

Creates the seven tenancy tables introduced by the multi-tenant resource
ownership refactor and seeds the canonical "default-*" rows so legacy data
backfilled by 0018 has a real foreign-key target.

The deterministic UUIDs match :mod:`aqp.config.defaults` so any code path
(tests, CLI, migration verifier) can compare against the canonical IDs
without round-tripping through Postgres.
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0017_tenancy_foundation"
down_revision = "0016_extraction_metadata"
branch_labels = None
depends_on = None


# Mirror of aqp.config.defaults — duplicated here so the migration is
# self-contained and survives a re-import of the config package.
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TEAM_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"
DEFAULT_LAB_ID = "00000000-0000-0000-0000-000000000006"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("billing_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_status", "organizations", ["status"])

    op.create_table(
        "teams",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "slug", name="uq_teams_org_slug"),
    )
    op.create_index("ix_teams_org_id", "teams", ["org_id"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("auth_subject", sa.String(length=240), nullable=True, unique=True),
        sa.Column("auth_provider", sa.String(length=64), nullable=False, server_default="local"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_auth_subject", "users", ["auth_subject"], unique=True)
    op.create_index("ix_users_auth_provider", "users", ["auth_provider"])
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="team"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "slug", name="uq_workspaces_org_slug"),
    )
    op.create_index("ix_workspaces_org_id", "workspaces", ["org_id"])
    op.create_index("ix_workspaces_visibility", "workspaces", ["visibility"])
    op.create_index("ix_workspaces_archived", "workspaces", ["archived"])

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_projects_workspace_slug"),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])
    op.create_index("ix_projects_archived", "projects", ["archived"])

    op.create_table(
        "labs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kernel_image", sa.String(length=240), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_active_at", sa.DateTime(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_labs_workspace_slug"),
    )
    op.create_index("ix_labs_workspace_id", "labs", ["workspace_id"])
    op.create_index("ix_labs_archived", "labs", ["archived"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"),
        sa.Column("live_control", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "granted_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("granted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "user_id", "scope_kind", "scope_id", "role",
            name="uq_memberships_user_scope_role",
        ),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_scope_kind", "memberships", ["scope_kind"])
    op.create_index("ix_memberships_scope_id", "memberships", ["scope_id"])
    op.create_index("ix_memberships_role", "memberships", ["role"])
    op.create_index("ix_memberships_scope", "memberships", ["scope_kind", "scope_id"])

    op.create_table(
        "config_overlays",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scope_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=False),
        sa.Column("namespace", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "scope_kind", "scope_id", "namespace",
            name="uq_config_overlays_scope_namespace",
        ),
    )
    op.create_index("ix_config_overlays_scope_kind", "config_overlays", ["scope_kind"])
    op.create_index("ix_config_overlays_scope_id", "config_overlays", ["scope_id"])
    op.create_index("ix_config_overlays_namespace", "config_overlays", ["namespace"])
    op.create_index("ix_config_overlays_scope", "config_overlays", ["scope_kind", "scope_id"])

    _seed_defaults()


def _seed_defaults() -> None:
    """Insert the canonical default-* rows + owner memberships for default-user."""
    bind = op.get_bind()
    now = datetime.utcnow()

    bind.execute(
        sa.text(
            """
            INSERT INTO organizations (id, slug, name, status, meta, created_at, updated_at)
            VALUES (:id, :slug, :name, :status, :meta, :now, :now)
            """
        ),
        {
            "id": DEFAULT_ORG_ID,
            "slug": "default",
            "name": "Default Organization",
            "status": "active",
            "meta": "{}",
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO teams (id, org_id, slug, name, description, meta, created_at, updated_at)
            VALUES (:id, :org_id, :slug, :name, :description, :meta, :now, :now)
            """
        ),
        {
            "id": DEFAULT_TEAM_ID,
            "org_id": DEFAULT_ORG_ID,
            "slug": "default",
            "name": "Default Team",
            "description": "Auto-created bucket for legacy single-tenant resources.",
            "meta": "{}",
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO users (
                id, email, display_name, auth_subject, auth_provider,
                status, meta, created_at, updated_at
            )
            VALUES (
                :id, :email, :display_name, :auth_subject, :auth_provider,
                :status, :meta, :now, :now
            )
            """
        ),
        {
            "id": DEFAULT_USER_ID,
            "email": "local@aqp.dev",
            "display_name": "Local User",
            "auth_subject": "local",
            "auth_provider": "local",
            "status": "active",
            "meta": "{}",
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO workspaces (
                id, org_id, slug, name, description, visibility,
                archived, settings, meta, created_at, updated_at
            )
            VALUES (
                :id, :org_id, :slug, :name, :description, :visibility,
                false, :settings, :meta, :now, :now
            )
            """
        ),
        {
            "id": DEFAULT_WORKSPACE_ID,
            "org_id": DEFAULT_ORG_ID,
            "slug": "default",
            "name": "Default Workspace",
            "description": "Shared bucket containing every legacy resource backfilled by 0018.",
            "visibility": "org",
            "settings": "{}",
            "meta": "{}",
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO projects (
                id, workspace_id, slug, name, description,
                archived, settings, meta, created_at, updated_at
            )
            VALUES (
                :id, :workspace_id, :slug, :name, :description,
                false, :settings, :meta, :now, :now
            )
            """
        ),
        {
            "id": DEFAULT_PROJECT_ID,
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "slug": "default",
            "name": "Default Project",
            "description": "Auto-created project for legacy strategies, backtests, and agents.",
            "settings": "{}",
            "meta": "{}",
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO labs (
                id, workspace_id, slug, name, description,
                archived, settings, meta, created_at, updated_at
            )
            VALUES (
                :id, :workspace_id, :slug, :name, :description,
                false, :settings, :meta, :now, :now
            )
            """
        ),
        {
            "id": DEFAULT_LAB_ID,
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "slug": "default",
            "name": "Default Lab",
            "description": "Auto-created notebook bucket for legacy RAG/memory state.",
            "settings": "{}",
            "meta": "{}",
            "now": now,
        },
    )

    membership_seed = (
        ("org", DEFAULT_ORG_ID),
        ("team", DEFAULT_TEAM_ID),
        ("workspace", DEFAULT_WORKSPACE_ID),
        ("project", DEFAULT_PROJECT_ID),
        ("lab", DEFAULT_LAB_ID),
    )
    for scope_kind, scope_id in membership_seed:
        bind.execute(
            sa.text(
                """
                INSERT INTO memberships (
                    id, user_id, scope_kind, scope_id, role,
                    live_control, granted_at, meta
                )
                VALUES (
                    :id, :user_id, :scope_kind, :scope_id, 'owner',
                    true, :now, '{}'
                )
                """
            ),
            {
                "id": f"00000000-0000-0000-1000-{_padded(scope_kind)}",
                "user_id": DEFAULT_USER_ID,
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                "now": now,
            },
        )


def _padded(scope_kind: str) -> str:
    """Build a stable 12-char hex tail for the seeded membership IDs."""
    base = scope_kind.encode("utf-8").hex()[:12]
    return base.ljust(12, "0")


def downgrade() -> None:
    op.drop_index("ix_config_overlays_scope", table_name="config_overlays")
    op.drop_index("ix_config_overlays_namespace", table_name="config_overlays")
    op.drop_index("ix_config_overlays_scope_id", table_name="config_overlays")
    op.drop_index("ix_config_overlays_scope_kind", table_name="config_overlays")
    op.drop_table("config_overlays")

    op.drop_index("ix_memberships_scope", table_name="memberships")
    op.drop_index("ix_memberships_role", table_name="memberships")
    op.drop_index("ix_memberships_scope_id", table_name="memberships")
    op.drop_index("ix_memberships_scope_kind", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("ix_labs_archived", table_name="labs")
    op.drop_index("ix_labs_workspace_id", table_name="labs")
    op.drop_table("labs")

    op.drop_index("ix_projects_archived", table_name="projects")
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_workspaces_archived", table_name="workspaces")
    op.drop_index("ix_workspaces_visibility", table_name="workspaces")
    op.drop_index("ix_workspaces_org_id", table_name="workspaces")
    op.drop_table("workspaces")

    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_auth_provider", table_name="users")
    op.drop_index("ix_users_auth_subject", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_teams_org_id", table_name="teams")
    op.drop_table("teams")

    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
