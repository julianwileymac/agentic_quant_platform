"""Strict default-tenancy normalization for deployment resources.

Revision ID: 0021_default_tenancy
Revises: 0020_bots
Create Date: 2026-05-03

This migration hardens the default tenancy chain for local-first operation:

1. Ensures canonical default org/team/user/workspace/project/lab rows exist.
2. Ensures default-user owner memberships exist for all seeded scopes.
3. Normalizes deployment-bearing resources into the default hierarchy.

Normalization target tables:

- model_deployments
- bots
- bot_versions
- bot_deployments
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0021_default_tenancy"
down_revision = "0020_bots"
branch_labels = None
depends_on = None


# Mirror of aqp.config.defaults to keep migration self-contained.
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TEAM_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"
DEFAULT_LAB_ID = "00000000-0000-0000-0000-000000000006"

DEFAULT_ORG_SLUG = "default"
DEFAULT_TEAM_SLUG = "default"
DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_PROJECT_SLUG = "default"
DEFAULT_LAB_SLUG = "default"

DEFAULT_ORG_NAME = "Default Organization"
DEFAULT_TEAM_NAME = "Default Team"
DEFAULT_WORKSPACE_NAME = "Default Workspace"
DEFAULT_PROJECT_NAME = "Default Project"
DEFAULT_LAB_NAME = "Default Lab"

DEFAULT_USER_EMAIL = "local@aqp.dev"
DEFAULT_USER_DISPLAY_NAME = "Local User"
DEFAULT_USER_AUTH_SUBJECT = "local"

NORMALIZED_TABLES = (
    "model_deployments",
    "bots",
    "bot_versions",
    "bot_deployments",
)


def upgrade() -> None:
    _ensure_default_identity_rows()
    _ensure_default_owner_memberships()
    _normalize_deployment_resources()


def _ensure_default_identity_rows() -> None:
    bind = op.get_bind()
    now = datetime.utcnow()
    empty_json = "{}"

    bind.execute(
        sa.text(
            """
            INSERT INTO organizations (id, slug, name, billing_email, status, meta, created_at, updated_at)
            VALUES (:id, :slug, :name, NULL, 'active', :meta, :now, :now)
            ON CONFLICT (id) DO UPDATE SET
                slug = EXCLUDED.slug,
                name = EXCLUDED.name,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": DEFAULT_ORG_ID,
            "slug": DEFAULT_ORG_SLUG,
            "name": DEFAULT_ORG_NAME,
            "meta": empty_json,
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO teams (id, org_id, slug, name, description, meta, created_at, updated_at)
            VALUES (:id, :org_id, :slug, :name, :description, :meta, :now, :now)
            ON CONFLICT (id) DO UPDATE SET
                org_id = EXCLUDED.org_id,
                slug = EXCLUDED.slug,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": DEFAULT_TEAM_ID,
            "org_id": DEFAULT_ORG_ID,
            "slug": DEFAULT_TEAM_SLUG,
            "name": DEFAULT_TEAM_NAME,
            "description": "Auto-created bucket for legacy single-tenant resources.",
            "meta": empty_json,
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO users (
                id, email, display_name, auth_subject, auth_provider,
                status, avatar_url, meta, last_login_at, created_at, updated_at
            )
            VALUES (
                :id, :email, :display_name, :auth_subject, 'local',
                'active', NULL, :meta, NULL, :now, :now
            )
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                auth_subject = EXCLUDED.auth_subject,
                auth_provider = EXCLUDED.auth_provider,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": DEFAULT_USER_ID,
            "email": DEFAULT_USER_EMAIL,
            "display_name": DEFAULT_USER_DISPLAY_NAME,
            "auth_subject": DEFAULT_USER_AUTH_SUBJECT,
            "meta": empty_json,
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
                :id, :org_id, :slug, :name, :description, 'org',
                false, :settings, :meta, :now, :now
            )
            ON CONFLICT (id) DO UPDATE SET
                org_id = EXCLUDED.org_id,
                slug = EXCLUDED.slug,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                visibility = EXCLUDED.visibility,
                archived = EXCLUDED.archived,
                settings = EXCLUDED.settings,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": DEFAULT_WORKSPACE_ID,
            "org_id": DEFAULT_ORG_ID,
            "slug": DEFAULT_WORKSPACE_SLUG,
            "name": DEFAULT_WORKSPACE_NAME,
            "description": "Shared bucket containing every legacy resource backfilled by 0018.",
            "settings": empty_json,
            "meta": empty_json,
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
            ON CONFLICT (id) DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                slug = EXCLUDED.slug,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                archived = EXCLUDED.archived,
                settings = EXCLUDED.settings,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": DEFAULT_PROJECT_ID,
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "slug": DEFAULT_PROJECT_SLUG,
            "name": DEFAULT_PROJECT_NAME,
            "description": "Auto-created project for legacy strategies, backtests, and agents.",
            "settings": empty_json,
            "meta": empty_json,
            "now": now,
        },
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO labs (
                id, workspace_id, slug, name, description,
                kernel_image, archived, last_active_at, settings, meta, created_at, updated_at
            )
            VALUES (
                :id, :workspace_id, :slug, :name, :description,
                NULL, false, NULL, :settings, :meta, :now, :now
            )
            ON CONFLICT (id) DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                slug = EXCLUDED.slug,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                archived = EXCLUDED.archived,
                settings = EXCLUDED.settings,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": DEFAULT_LAB_ID,
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "slug": DEFAULT_LAB_SLUG,
            "name": DEFAULT_LAB_NAME,
            "description": "Auto-created notebook bucket for legacy RAG/memory state.",
            "settings": empty_json,
            "meta": empty_json,
            "now": now,
        },
    )


def _ensure_default_owner_memberships() -> None:
    bind = op.get_bind()
    now = datetime.utcnow()
    scope_pairs = (
        ("org", DEFAULT_ORG_ID),
        ("team", DEFAULT_TEAM_ID),
        ("workspace", DEFAULT_WORKSPACE_ID),
        ("project", DEFAULT_PROJECT_ID),
        ("lab", DEFAULT_LAB_ID),
    )
    for scope_kind, scope_id in scope_pairs:
        bind.execute(
            sa.text(
                """
                INSERT INTO memberships (
                    id, user_id, scope_kind, scope_id, role,
                    live_control, granted_by, granted_at, expires_at, meta
                )
                VALUES (
                    :id, :user_id, :scope_kind, :scope_id, 'owner',
                    true, :user_id, :granted_at, NULL, '{}'
                )
                ON CONFLICT ON CONSTRAINT uq_memberships_user_scope_role
                DO UPDATE SET
                    live_control = EXCLUDED.live_control,
                    granted_by = EXCLUDED.granted_by
                """
            ),
            {
                "id": _membership_id(scope_kind),
                "user_id": DEFAULT_USER_ID,
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                "granted_at": now,
            },
        )


def _membership_id(scope_kind: str) -> str:
    return f"00000000-0000-0000-1000-{_padded(scope_kind)}"


def _padded(scope_kind: str) -> str:
    base = scope_kind.encode("utf-8").hex()[:12]
    return base.ljust(12, "0")


def _normalize_deployment_resources() -> None:
    bind = op.get_bind()
    params = {
        "owner_user_id": DEFAULT_USER_ID,
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "project_id": DEFAULT_PROJECT_ID,
    }
    for table in NORMALIZED_TABLES:
        bind.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET owner_user_id = :owner_user_id,
                    workspace_id = :workspace_id,
                    project_id = :project_id
                WHERE owner_user_id IS NULL
                   OR owner_user_id <> :owner_user_id
                   OR workspace_id IS NULL
                   OR workspace_id <> :workspace_id
                   OR project_id IS NULL
                   OR project_id <> :project_id
                """
            ),
            params,
        )


def downgrade() -> None:
    """Irreversible data-normalization migration."""
    # Data was normalized in-place; we intentionally do not restore previous
    # per-row ownership values.
    pass
