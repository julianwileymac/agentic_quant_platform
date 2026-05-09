"""Strategy regime memory table for the Phase-4 iterative optimisation loop.

Revision ID: 0030_strategy_regime_memory
Revises: 0029_backtest_run_artifact
Create Date: 2026-05-09

AgentQuant-style cross-session strategy memory: when the agent
backtests a strategy under regime X and finds a Sharpe > threshold,
the row stored here lets a later session warm-start with the same
parameters under the same regime. Workspace-scoped per
:class:`ProjectScopedMixin` so tenants build up isolated knowledge.

The unique key ``(workspace_id, strategy_id, regime, params_hash)``
keeps re-fits with the same parameter set idempotent — multiple
backtests with the same params upsert into a single row whose
``best_sharpe`` is the running max.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0030_strategy_regime_memory"
down_revision = "0029_backtest_run_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_regime_memory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_id", sa.String(length=160), nullable=False),
        sa.Column("regime", sa.String(length=64), nullable=False),
        sa.Column("params_hash", sa.String(length=64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("best_sharpe", sa.Float(), nullable=True),
        sa.Column("best_sortino", sa.Float(), nullable=True),
        sa.Column("best_calmar", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("n_observations", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("backtest_run_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.JSON(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin columns
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "strategy_id", "regime", "params_hash",
            name="uq_strategy_regime_memory_ws_strategy_regime_hash",
        ),
    )
    op.create_index(
        "ix_strategy_regime_memory_lookup",
        "strategy_regime_memory",
        ["workspace_id", "strategy_id", "regime", "best_sharpe"],
    )
    op.create_index(
        "ix_strategy_regime_memory_strategy_id",
        "strategy_regime_memory",
        ["strategy_id"],
    )
    op.create_index(
        "ix_strategy_regime_memory_regime",
        "strategy_regime_memory",
        ["regime"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_regime_memory_regime", table_name="strategy_regime_memory")
    op.drop_index("ix_strategy_regime_memory_strategy_id", table_name="strategy_regime_memory")
    op.drop_index("ix_strategy_regime_memory_lookup", table_name="strategy_regime_memory")
    op.drop_table("strategy_regime_memory")
