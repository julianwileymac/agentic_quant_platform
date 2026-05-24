"""dbt mesh project registry (Phase 2 — dbt plane, plan section 6).

Revision ID: 0073_dbt_mesh_projects
Revises: 0072_airbyte_dataset_kind
Create Date: 2026-05-24

Adds ``dbt_mesh_projects`` — one row per dbt project participating
in the AQP mesh. The shared aqp-dbt-core publishes its manifest to
S3 via the :mod:`aqp.data.dbt.loom_registry` sidecar; per-team
projects (equities / derivatives / macro / ...) declare their
upstream dependencies in ``dependency_slugs``.

The table is workspace-scoped + RLS-protected per AGENTS rule 51.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0073_dbt_mesh_projects"
down_revision = "0072_airbyte_dataset_kind"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "dbt_mesh_projects",
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
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("manifest_s3_uri", sa.String(500), nullable=True),
        sa.Column("git_repo", sa.String(500), nullable=True),
        sa.Column("git_sha", sa.String(120), nullable=True),
        sa.Column(
            "dependency_slugs",
            sa.JSON,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "access_level",
            sa.String(16),
            nullable=False,
            server_default="protected",
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
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
        "ix_dbt_mesh_projects_owner_user_id", "dbt_mesh_projects", ["owner_user_id"]
    )
    op.create_index(
        "ix_dbt_mesh_projects_workspace_id", "dbt_mesh_projects", ["workspace_id"]
    )
    op.create_index("ix_dbt_mesh_projects_slug", "dbt_mesh_projects", ["slug"])
    op.create_index(
        "ix_dbt_mesh_projects_is_active", "dbt_mesh_projects", ["is_active"]
    )

    if not _is_postgres():
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                ALTER TABLE dbt_mesh_projects ENABLE ROW LEVEL SECURITY;
                ALTER TABLE dbt_mesh_projects FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_dbt_mesh_projects ON dbt_mesh_projects;
                CREATE POLICY tenant_isolation_dbt_mesh_projects ON dbt_mesh_projects
                    USING (workspace_id IS NULL OR workspace_id =
                           current_setting('app.current_workspace_id', true));
                GRANT SELECT, INSERT, UPDATE, DELETE ON dbt_mesh_projects TO app_runtime;
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
                    WHERE table_name = 'dbt_mesh_projects'
                ) THEN
                    DROP POLICY IF EXISTS tenant_isolation_dbt_mesh_projects ON dbt_mesh_projects;
                    ALTER TABLE dbt_mesh_projects NO FORCE ROW LEVEL SECURITY;
                    ALTER TABLE dbt_mesh_projects DISABLE ROW LEVEL SECURITY;
                END IF;
            END
            $$;
            """
        )
    op.drop_index("ix_dbt_mesh_projects_is_active", table_name="dbt_mesh_projects")
    op.drop_index("ix_dbt_mesh_projects_slug", table_name="dbt_mesh_projects")
    op.drop_index("ix_dbt_mesh_projects_workspace_id", table_name="dbt_mesh_projects")
    op.drop_index("ix_dbt_mesh_projects_owner_user_id", table_name="dbt_mesh_projects")
    op.drop_table("dbt_mesh_projects")
