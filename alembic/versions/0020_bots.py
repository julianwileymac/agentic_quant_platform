"""Bot entity: bots, bot_versions, bot_deployments.

Revision ID: 0020_bots
Revises: 0019_ownership_enforce
Create Date: 2026-05-03

Introduces the first-class :class:`Bot` aggregate as the smallest
self-contained, deployable unit on AQP. Mirrors the proven
``agent_specs`` / ``agent_spec_versions`` pattern (immutable hash-locked
snapshots + a logical row pointing at the latest version) and adds a
``bot_deployments`` ledger for every backtest / paper / chat / k8s
invocation driven through :class:`aqp.bots.runtime.BotRuntime`.

Tenancy
-------

Every table carries the ``ProjectScopedMixin`` columns (``owner_user_id``,
``workspace_id``, ``project_id``) added by 0017–0019, so the multi-tenant
ownership chain reaches Bot rows out of the box.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_bots"
down_revision = "0019_ownership_enforce"
branch_labels = None
depends_on = None


# Mirror of aqp.config.defaults so the migration is self-contained.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="trading",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "current_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("spec_yaml", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="draft"
        ),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        # Tenancy (NOT NULL after 0019; default seed for legacy callers).
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
            server_default=DEFAULT_USER_ID,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=False,
            server_default=DEFAULT_WORKSPACE_ID,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_PROJECT_ID,
        ),
        sa.UniqueConstraint("project_id", "slug", name="uq_bots_project_slug"),
    )
    op.create_index("ix_bots_slug", "bots", ["slug"])
    op.create_index("ix_bots_kind", "bots", ["kind"])
    op.create_index("ix_bots_status", "bots", ["status"])
    op.create_index("ix_bots_owner_user_id", "bots", ["owner_user_id"])
    op.create_index("ix_bots_workspace_id", "bots", ["workspace_id"])
    op.create_index("ix_bots_project_id", "bots", ["project_id"])

    op.create_table(
        "bot_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "bot_id",
            sa.String(length=36),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
            server_default=DEFAULT_USER_ID,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=False,
            server_default=DEFAULT_WORKSPACE_ID,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_PROJECT_ID,
        ),
        sa.UniqueConstraint(
            "bot_id", "spec_hash", name="uq_bot_versions_bot_hash"
        ),
        sa.UniqueConstraint(
            "bot_id", "version", name="uq_bot_versions_bot_version"
        ),
    )
    op.create_index("ix_bot_versions_bot_id", "bot_versions", ["bot_id"])
    op.create_index("ix_bot_versions_spec_hash", "bot_versions", ["spec_hash"])
    op.create_index(
        "ix_bot_versions_bot_version",
        "bot_versions",
        ["bot_id", "version"],
    )
    op.create_index(
        "ix_bot_versions_owner_user_id", "bot_versions", ["owner_user_id"]
    )
    op.create_index(
        "ix_bot_versions_workspace_id", "bot_versions", ["workspace_id"]
    )
    op.create_index(
        "ix_bot_versions_project_id", "bot_versions", ["project_id"]
    )

    op.create_table(
        "bot_deployments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "bot_id",
            sa.String(length=36),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("bot_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("manifest_yaml", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
            server_default=DEFAULT_USER_ID,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=False,
            server_default=DEFAULT_WORKSPACE_ID,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_PROJECT_ID,
        ),
    )
    op.create_index("ix_bot_deployments_bot_id", "bot_deployments", ["bot_id"])
    op.create_index(
        "ix_bot_deployments_version_id", "bot_deployments", ["version_id"]
    )
    op.create_index("ix_bot_deployments_target", "bot_deployments", ["target"])
    op.create_index("ix_bot_deployments_task_id", "bot_deployments", ["task_id"])
    op.create_index("ix_bot_deployments_status", "bot_deployments", ["status"])
    op.create_index(
        "ix_bot_deployments_status_started",
        "bot_deployments",
        ["status", "started_at"],
    )
    op.create_index(
        "ix_bot_deployments_owner_user_id", "bot_deployments", ["owner_user_id"]
    )
    op.create_index(
        "ix_bot_deployments_workspace_id", "bot_deployments", ["workspace_id"]
    )
    op.create_index(
        "ix_bot_deployments_project_id", "bot_deployments", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_bot_deployments_project_id", table_name="bot_deployments")
    op.drop_index("ix_bot_deployments_workspace_id", table_name="bot_deployments")
    op.drop_index("ix_bot_deployments_owner_user_id", table_name="bot_deployments")
    op.drop_index(
        "ix_bot_deployments_status_started", table_name="bot_deployments"
    )
    op.drop_index("ix_bot_deployments_status", table_name="bot_deployments")
    op.drop_index("ix_bot_deployments_task_id", table_name="bot_deployments")
    op.drop_index("ix_bot_deployments_target", table_name="bot_deployments")
    op.drop_index("ix_bot_deployments_version_id", table_name="bot_deployments")
    op.drop_index("ix_bot_deployments_bot_id", table_name="bot_deployments")
    op.drop_table("bot_deployments")

    op.drop_index("ix_bot_versions_project_id", table_name="bot_versions")
    op.drop_index("ix_bot_versions_workspace_id", table_name="bot_versions")
    op.drop_index("ix_bot_versions_owner_user_id", table_name="bot_versions")
    op.drop_index("ix_bot_versions_bot_version", table_name="bot_versions")
    op.drop_index("ix_bot_versions_spec_hash", table_name="bot_versions")
    op.drop_index("ix_bot_versions_bot_id", table_name="bot_versions")
    op.drop_table("bot_versions")

    op.drop_index("ix_bots_project_id", table_name="bots")
    op.drop_index("ix_bots_workspace_id", table_name="bots")
    op.drop_index("ix_bots_owner_user_id", table_name="bots")
    op.drop_index("ix_bots_status", table_name="bots")
    op.drop_index("ix_bots_kind", table_name="bots")
    op.drop_index("ix_bots_slug", table_name="bots")
    op.drop_table("bots")
