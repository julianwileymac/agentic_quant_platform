"""add optimization_runs + optimization_trials + crew_runs

Revision ID: 0003_optimizer_and_crew
Revises: 0002_strategy_versions_tests
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_optimizer_and_crew"
down_revision = "0002_strategy_versions_tests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("strategy_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("run_name", sa.String(length=240), nullable=False, server_default="sweep"),
        sa.Column("method", sa.String(length=32), nullable=False, server_default="grid"),
        sa.Column("metric", sa.String(length=64), nullable=False, server_default="sharpe"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued", index=True),
        sa.Column("n_trials", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_trial_id", sa.String(length=36), nullable=True),
        sa.Column("best_metric_value", sa.Float(), nullable=True),
        sa.Column("parameter_space", sa.JSON(), nullable=True),
        sa.Column("base_config", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
    )

    op.create_table(
        "optimization_trials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("backtest_id", sa.String(length=36), nullable=True),
        sa.Column("trial_index", sa.Integer(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("sharpe", sa.Float(), nullable=True),
        sa.Column("sortino", sa.Float(), nullable=True),
        sa.Column("total_return", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("final_equity", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["optimization_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["backtest_id"], ["backtest_runs.id"]),
    )

    op.create_table(
        "crew_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=120), nullable=False, unique=True, index=True),
        sa.Column("crew_name", sa.String(length=120), nullable=False, server_default="research"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued", index=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("events", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
    )


def downgrade() -> None:
    op.drop_table("crew_runs")
    op.drop_table("optimization_trials")
    op.drop_table("optimization_runs")
