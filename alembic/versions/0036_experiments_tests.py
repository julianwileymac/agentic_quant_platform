"""Experiments + Tests umbrella tables.

Revision ID: 0036_experiments_tests
Revises: 0035_research_papers
Create Date: 2026-05-16

Adds two new tables that sit *above* the existing typed run tables
(``ml_experiment_runs``, ``rl_runs``, ``analysis_runs``,
``backtest_runs``, ``bot_deployments``, ``strategy_tests``,
``paper_trading_runs``, ``agent_runs_v2``):

- ``experiments`` — the user-driven container; what they were trying.
- ``tests`` — pass/fail assertions evaluated against an experiment.

The companion :file:`0037_experiment_test_linkage.py` adds the FK
columns to the typed run tables.

AGENTS.md rule 6: this migration is **immutable** once shipped — any
future schema change goes into a new revision.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0036_experiments_tests"
down_revision = "0035_research_papers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aqp_experiments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="research"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("parent_experiment_id", sa.String(length=36), nullable=True),
        sa.Column("lab_id", sa.String(length=36), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["parent_experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug", name="uq_aqp_experiments_project_slug"),
    )
    op.create_index("ix_aqp_experiments_slug", "aqp_experiments", ["slug"])
    op.create_index("ix_aqp_experiments_kind", "aqp_experiments", ["kind"])
    op.create_index("ix_aqp_experiments_status", "aqp_experiments", ["status"])
    op.create_index(
        "ix_aqp_experiments_parent_experiment_id",
        "aqp_experiments",
        ["parent_experiment_id"],
    )
    op.create_index("ix_aqp_experiments_lab_id", "aqp_experiments", ["lab_id"])
    op.create_index("ix_aqp_experiments_owner_user_id", "aqp_experiments", ["owner_user_id"])
    op.create_index("ix_aqp_experiments_workspace_id", "aqp_experiments", ["workspace_id"])
    op.create_index("ix_aqp_experiments_project_id", "aqp_experiments", ["project_id"])
    op.create_index(
        "ix_aqp_experiments_kind_status", "aqp_experiments", ["kind", "status"]
    )
    op.create_index(
        "ix_aqp_experiments_workspace_project",
        "aqp_experiments",
        ["workspace_id", "project_id"],
    )
    op.create_index(
        "ix_aqp_experiments_parent_started",
        "aqp_experiments",
        ["parent_experiment_id", "started_at"],
    )

    op.create_table(
        "aqp_tests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "assertion_kind",
            sa.String(length=32),
            nullable=False,
            server_default="metric_threshold",
        ),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("run_ref_table", sa.String(length=64), nullable=True),
        sa.Column("run_ref_id", sa.String(length=36), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "slug", name="uq_aqp_tests_experiment_slug"),
    )
    op.create_index("ix_aqp_tests_experiment_id", "aqp_tests", ["experiment_id"])
    op.create_index("ix_aqp_tests_slug", "aqp_tests", ["slug"])
    op.create_index("ix_aqp_tests_assertion_kind", "aqp_tests", ["assertion_kind"])
    op.create_index("ix_aqp_tests_passed", "aqp_tests", ["passed"])
    op.create_index("ix_aqp_tests_owner_user_id", "aqp_tests", ["owner_user_id"])
    op.create_index("ix_aqp_tests_workspace_id", "aqp_tests", ["workspace_id"])
    op.create_index("ix_aqp_tests_project_id", "aqp_tests", ["project_id"])
    op.create_index(
        "ix_aqp_tests_assertion_passed", "aqp_tests", ["assertion_kind", "passed"]
    )


def downgrade() -> None:
    op.drop_index("ix_aqp_tests_assertion_passed", table_name="aqp_tests")
    op.drop_index("ix_aqp_tests_project_id", table_name="aqp_tests")
    op.drop_index("ix_aqp_tests_workspace_id", table_name="aqp_tests")
    op.drop_index("ix_aqp_tests_owner_user_id", table_name="aqp_tests")
    op.drop_index("ix_aqp_tests_passed", table_name="aqp_tests")
    op.drop_index("ix_aqp_tests_assertion_kind", table_name="aqp_tests")
    op.drop_index("ix_aqp_tests_slug", table_name="aqp_tests")
    op.drop_index("ix_aqp_tests_experiment_id", table_name="aqp_tests")
    op.drop_table("aqp_tests")

    op.drop_index("ix_aqp_experiments_parent_started", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_workspace_project", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_kind_status", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_project_id", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_workspace_id", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_owner_user_id", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_lab_id", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_parent_experiment_id", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_status", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_kind", table_name="aqp_experiments")
    op.drop_index("ix_aqp_experiments_slug", table_name="aqp_experiments")
    op.drop_table("aqp_experiments")
