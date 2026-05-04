"""ML alpha-backtest linkage tables and FKs.

Revision ID: 0025_ml_alpha_backtest_linkage
Revises: 0024_data_layer_expansion
Create Date: 2026-05-03

Adds the persistence layer for the ML engine major expansion:

- Adds FK columns on ``backtest_runs`` linking back to the trained model
  (``model_version_id``), the ML experiment run that trained it
  (``ml_experiment_run_id``), the experiment plan that generated it
  (``experiment_plan_id``), and the deployment used to bridge model->alpha
  (``model_deployment_id``). All four are nullable so legacy rows are not
  invalidated.
- ``ml_alpha_backtest_runs`` — combined experiment record that joins an
  ``MLExperimentRun`` (training) to a ``BacktestRun`` (deployment as alpha)
  in a single tracked unit. Stores combined ML + trading metrics under one
  MLflow parent run.
- ``ml_prediction_audit`` — capped per-bar prediction sample for an
  alpha-backtest run, opt-in via ``AQP_ML_PREDICTION_AUDIT_ENABLED``.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_ml_alpha_backtest_linkage"
down_revision = "0024_data_layer_expansion"
branch_labels = None
depends_on = None


DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"


def _project_scope_columns() -> list[sa.Column]:
    return [
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
    ]


def _project_scope_indexes(table_name: str) -> None:
    op.create_index(f"ix_{table_name}_owner_user_id", table_name, ["owner_user_id"])
    op.create_index(f"ix_{table_name}_workspace_id", table_name, ["workspace_id"])
    op.create_index(f"ix_{table_name}_project_id", table_name, ["project_id"])


def upgrade() -> None:
    # ---- Add FK columns to backtest_runs ----
    with op.batch_alter_table("backtest_runs") as batch:
        batch.add_column(
            sa.Column(
                "model_version_id",
                sa.String(length=36),
                sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "ml_experiment_run_id",
                sa.String(length=36),
                sa.ForeignKey("ml_experiment_runs.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "experiment_plan_id",
                sa.String(length=36),
                sa.ForeignKey("experiment_plans.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "model_deployment_id",
                sa.String(length=36),
                sa.ForeignKey("model_deployments.id", ondelete="SET NULL"),
                nullable=True,
            )
        )

    op.create_index(
        "ix_backtest_runs_model_version_id",
        "backtest_runs",
        ["model_version_id"],
    )
    op.create_index(
        "ix_backtest_runs_ml_experiment_run_id",
        "backtest_runs",
        ["ml_experiment_run_id"],
    )
    op.create_index(
        "ix_backtest_runs_experiment_plan_id",
        "backtest_runs",
        ["experiment_plan_id"],
    )
    op.create_index(
        "ix_backtest_runs_model_deployment_id",
        "backtest_runs",
        ["model_deployment_id"],
    )

    # ---- ml_alpha_backtest_runs ----
    op.create_table(
        "ml_alpha_backtest_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column(
            "run_name",
            sa.String(length=240),
            nullable=False,
            server_default="alpha-backtest",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "ml_experiment_run_id",
            sa.String(length=36),
            sa.ForeignKey("ml_experiment_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "backtest_run_id",
            sa.String(length=36),
            sa.ForeignKey("backtest_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "model_version_id",
            sa.String(length=36),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "model_deployment_id",
            sa.String(length=36),
            sa.ForeignKey("model_deployments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "experiment_plan_id",
            sa.String(length=36),
            sa.ForeignKey("experiment_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mlflow_run_id", sa.String(length=120), nullable=True),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("ml_metrics", sa.JSON(), nullable=True),
        sa.Column("trading_metrics", sa.JSON(), nullable=True),
        sa.Column("combined_metrics", sa.JSON(), nullable=True),
        sa.Column("attribution", sa.JSON(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    _project_scope_indexes("ml_alpha_backtest_runs")
    op.create_index(
        "ix_ml_alpha_backtest_runs_status",
        "ml_alpha_backtest_runs",
        ["status"],
    )
    op.create_index(
        "ix_ml_alpha_backtest_runs_ml_run",
        "ml_alpha_backtest_runs",
        ["ml_experiment_run_id"],
    )
    op.create_index(
        "ix_ml_alpha_backtest_runs_bt_run",
        "ml_alpha_backtest_runs",
        ["backtest_run_id"],
    )
    op.create_index(
        "ix_ml_alpha_backtest_runs_model_version",
        "ml_alpha_backtest_runs",
        ["model_version_id"],
    )

    # ---- ml_prediction_audit ----
    op.create_table(
        "ml_prediction_audit",
        sa.Column("id", sa.String(length=36), primary_key=True),
        *_project_scope_columns(),
        sa.Column(
            "alpha_backtest_run_id",
            sa.String(length=36),
            sa.ForeignKey("ml_alpha_backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vt_symbol", sa.String(length=40), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("prediction", sa.Float(), nullable=False),
        sa.Column("label", sa.Float(), nullable=True),
        sa.Column("position_after", sa.Float(), nullable=True),
        sa.Column("pnl_after_bar", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    _project_scope_indexes("ml_prediction_audit")
    op.create_index(
        "ix_ml_prediction_audit_run_ts",
        "ml_prediction_audit",
        ["alpha_backtest_run_id", "ts"],
    )
    op.create_index(
        "ix_ml_prediction_audit_run_symbol",
        "ml_prediction_audit",
        ["alpha_backtest_run_id", "vt_symbol"],
    )


def downgrade() -> None:
    op.drop_index("ix_ml_prediction_audit_run_symbol", table_name="ml_prediction_audit")
    op.drop_index("ix_ml_prediction_audit_run_ts", table_name="ml_prediction_audit")
    op.drop_index("ix_ml_prediction_audit_project_id", table_name="ml_prediction_audit")
    op.drop_index("ix_ml_prediction_audit_workspace_id", table_name="ml_prediction_audit")
    op.drop_index("ix_ml_prediction_audit_owner_user_id", table_name="ml_prediction_audit")
    op.drop_table("ml_prediction_audit")

    op.drop_index(
        "ix_ml_alpha_backtest_runs_model_version",
        table_name="ml_alpha_backtest_runs",
    )
    op.drop_index(
        "ix_ml_alpha_backtest_runs_bt_run", table_name="ml_alpha_backtest_runs"
    )
    op.drop_index(
        "ix_ml_alpha_backtest_runs_ml_run", table_name="ml_alpha_backtest_runs"
    )
    op.drop_index(
        "ix_ml_alpha_backtest_runs_status", table_name="ml_alpha_backtest_runs"
    )
    op.drop_index(
        "ix_ml_alpha_backtest_runs_project_id",
        table_name="ml_alpha_backtest_runs",
    )
    op.drop_index(
        "ix_ml_alpha_backtest_runs_workspace_id",
        table_name="ml_alpha_backtest_runs",
    )
    op.drop_index(
        "ix_ml_alpha_backtest_runs_owner_user_id",
        table_name="ml_alpha_backtest_runs",
    )
    op.drop_table("ml_alpha_backtest_runs")

    op.drop_index(
        "ix_backtest_runs_model_deployment_id", table_name="backtest_runs"
    )
    op.drop_index(
        "ix_backtest_runs_experiment_plan_id", table_name="backtest_runs"
    )
    op.drop_index(
        "ix_backtest_runs_ml_experiment_run_id", table_name="backtest_runs"
    )
    op.drop_index(
        "ix_backtest_runs_model_version_id", table_name="backtest_runs"
    )

    with op.batch_alter_table("backtest_runs") as batch:
        batch.drop_column("model_deployment_id")
        batch.drop_column("experiment_plan_id")
        batch.drop_column("ml_experiment_run_id")
        batch.drop_column("model_version_id")
