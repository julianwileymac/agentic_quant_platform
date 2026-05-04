"""Persist ML experiment and interactive test runs.

Revision ID: 0022_mlops_experiment_runs
Revises: 0021_default_tenancy
Create Date: 2026-05-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_mlops_experiment_runs"
down_revision = "0021_default_tenancy"
branch_labels = None
depends_on = None

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"


def upgrade() -> None:
    op.create_table(
        "ml_experiment_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column("run_name", sa.String(length=240), nullable=False, server_default="ml-experiment"),
        sa.Column("experiment_type", sa.String(length=40), nullable=False, server_default="alpha"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("framework", sa.String(length=80), nullable=True),
        sa.Column("model_class", sa.String(length=120), nullable=True),
        sa.Column("model_version_id", sa.String(length=36), sa.ForeignKey("model_versions.id"), nullable=True),
        sa.Column("experiment_plan_id", sa.String(length=36), sa.ForeignKey("experiment_plans.id"), nullable=True),
        sa.Column("dataset_version_id", sa.String(length=36), sa.ForeignKey("dataset_versions.id"), nullable=True),
        sa.Column("split_plan_id", sa.String(length=36), sa.ForeignKey("split_plans.id"), nullable=True),
        sa.Column("pipeline_recipe_id", sa.String(length=36), sa.ForeignKey("pipeline_recipes.id"), nullable=True),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("mlflow_run_id", sa.String(length=120), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("artifacts", sa.JSON(), nullable=True),
        sa.Column("prediction_sample", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_USER_ID,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
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
    op.create_index("ix_ml_experiment_runs_task_id", "ml_experiment_runs", ["task_id"])
    op.create_index("ix_ml_experiment_runs_experiment_type", "ml_experiment_runs", ["experiment_type"])
    op.create_index("ix_ml_experiment_runs_status", "ml_experiment_runs", ["status"])
    op.create_index("ix_ml_experiment_runs_framework", "ml_experiment_runs", ["framework"])
    op.create_index("ix_ml_experiment_runs_model_class", "ml_experiment_runs", ["model_class"])
    op.create_index("ix_ml_experiment_runs_model_version_id", "ml_experiment_runs", ["model_version_id"])
    op.create_index("ix_ml_experiment_runs_experiment_plan_id", "ml_experiment_runs", ["experiment_plan_id"])
    op.create_index("ix_ml_experiment_runs_dataset_version_id", "ml_experiment_runs", ["dataset_version_id"])
    op.create_index("ix_ml_experiment_runs_split_plan_id", "ml_experiment_runs", ["split_plan_id"])
    op.create_index("ix_ml_experiment_runs_pipeline_recipe_id", "ml_experiment_runs", ["pipeline_recipe_id"])
    op.create_index("ix_ml_experiment_runs_dataset_hash", "ml_experiment_runs", ["dataset_hash"])
    op.create_index("ix_ml_experiment_runs_mlflow_run_id", "ml_experiment_runs", ["mlflow_run_id"])
    op.create_index("ix_ml_experiment_runs_started_at", "ml_experiment_runs", ["started_at"])
    op.create_index("ix_ml_experiment_runs_owner_user_id", "ml_experiment_runs", ["owner_user_id"])
    op.create_index("ix_ml_experiment_runs_workspace_id", "ml_experiment_runs", ["workspace_id"])
    op.create_index("ix_ml_experiment_runs_project_id", "ml_experiment_runs", ["project_id"])
    op.create_index(
        "ix_ml_experiment_runs_type_status",
        "ml_experiment_runs",
        ["experiment_type", "status"],
    )
    op.create_index(
        "ix_ml_experiment_runs_model_created",
        "ml_experiment_runs",
        ["model_class", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ml_experiment_runs_model_created", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_type_status", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_project_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_workspace_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_owner_user_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_started_at", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_mlflow_run_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_dataset_hash", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_pipeline_recipe_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_split_plan_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_dataset_version_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_experiment_plan_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_model_version_id", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_model_class", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_framework", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_status", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_experiment_type", table_name="ml_experiment_runs")
    op.drop_index("ix_ml_experiment_runs_task_id", table_name="ml_experiment_runs")
    op.drop_table("ml_experiment_runs")
