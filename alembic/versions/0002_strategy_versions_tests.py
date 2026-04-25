"""add strategy_versions + strategy_tests

Revision ID: 0002_strategy_versions_tests
Revises: 0001_paper_trading_runs
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_strategy_versions_tests"
down_revision = "0001_paper_trading_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("strategy_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_yaml", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("dataset_hash", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_strategy_versions_strategy_version",
        "strategy_versions",
        ["strategy_id", "version"],
    )

    op.create_table(
        "strategy_tests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("strategy_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("backtest_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("start", sa.DateTime(), nullable=True),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("sharpe", sa.Float(), nullable=True),
        sa.Column("sortino", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("total_return", sa.Float(), nullable=True),
        sa.Column("final_equity", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("engine", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["strategy_versions.id"]),
        sa.ForeignKeyConstraint(["backtest_id"], ["backtest_runs.id"]),
    )


def downgrade() -> None:
    op.drop_table("strategy_tests")
    op.drop_index("ix_strategy_versions_strategy_version", table_name="strategy_versions")
    op.drop_table("strategy_versions")
