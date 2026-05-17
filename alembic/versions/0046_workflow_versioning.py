"""Phase 5 - workflow registry + versioning + run ledger.

Revision ID: 0046_workflow_versioning
Revises: 0045_pgvector_foundation
Create Date: 2026-05-17

Adds three new tables for the additive orchestration control plane:

- ``workflow_specs`` (logical workflow, latest active version)
- ``workflow_spec_versions`` (immutable, hash-locked snapshots)
- ``workflow_runs`` (per-execution ledger row + experiment_id + test_id
  FKs per AGENTS rule 34)

The migration is strictly additive - existing tables are untouched.
Downgrade returns the database to ``0045_pgvector_foundation``.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0046_workflow_versioning"
down_revision = "0045_pgvector_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_specs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("adapter", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # Tenancy columns from ProjectScopedMixin.
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint("name", name="uq_workflow_specs_name"),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_workflow_specs_name", "workflow_specs", ["name"], unique=True
    )
    op.create_index(
        "ix_workflow_specs_owner_user_id",
        "workflow_specs",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_workflow_specs_workspace_id", "workflow_specs", ["workspace_id"]
    )
    op.create_index(
        "ix_workflow_specs_project_id", "workflow_specs", ["project_id"]
    )

    op.create_table(
        "workflow_spec_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("spec_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["spec_id"], ["workflow_specs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("spec_hash", name="uq_workflow_spec_versions_hash"),
    )
    op.create_index(
        "ix_workflow_spec_versions_spec_id", "workflow_spec_versions", ["spec_id"]
    )
    op.create_index(
        "ix_workflow_spec_versions_spec_hash",
        "workflow_spec_versions",
        ["spec_hash"],
        unique=True,
    )
    op.create_index(
        "ix_workflow_spec_versions_spec_version",
        "workflow_spec_versions",
        ["spec_id", "version"],
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workflow_spec_name", sa.String(length=160), nullable=False),
        sa.Column("spec_version_id", sa.String(length=36), nullable=True),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("inputs", sa.JSON(), nullable=True),
        sa.Column("final_state", sa.JSON(), nullable=True),
        sa.Column("breadcrumbs", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("n_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_rag_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "halted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("test_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["spec_version_id"],
            ["workflow_spec_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["test_id"], ["tests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_workflow_runs_workflow_spec_name", "workflow_runs", ["workflow_spec_name"])
    op.create_index("ix_workflow_runs_spec_version_id", "workflow_runs", ["spec_version_id"])
    op.create_index("ix_workflow_runs_parent_run_id", "workflow_runs", ["parent_run_id"])
    op.create_index("ix_workflow_runs_task_id", "workflow_runs", ["task_id"])
    op.create_index("ix_workflow_runs_session_id", "workflow_runs", ["session_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_experiment_id", "workflow_runs", ["experiment_id"])
    op.create_index("ix_workflow_runs_test_id", "workflow_runs", ["test_id"])
    op.create_index("ix_workflow_runs_owner_user_id", "workflow_runs", ["owner_user_id"])
    op.create_index("ix_workflow_runs_workspace_id", "workflow_runs", ["workspace_id"])
    op.create_index("ix_workflow_runs_project_id", "workflow_runs", ["project_id"])
    op.create_index(
        "ix_workflow_runs_status_started",
        "workflow_runs",
        ["status", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_status_started", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_project_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_owner_user_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_test_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_experiment_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_session_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_task_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_parent_run_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_spec_version_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_spec_name", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index(
        "ix_workflow_spec_versions_spec_version", table_name="workflow_spec_versions"
    )
    op.drop_index(
        "ix_workflow_spec_versions_spec_hash", table_name="workflow_spec_versions"
    )
    op.drop_index(
        "ix_workflow_spec_versions_spec_id", table_name="workflow_spec_versions"
    )
    op.drop_table("workflow_spec_versions")

    op.drop_index("ix_workflow_specs_project_id", table_name="workflow_specs")
    op.drop_index("ix_workflow_specs_workspace_id", table_name="workflow_specs")
    op.drop_index("ix_workflow_specs_owner_user_id", table_name="workflow_specs")
    op.drop_index("ix_workflow_specs_name", table_name="workflow_specs")
    op.drop_table("workflow_specs")
