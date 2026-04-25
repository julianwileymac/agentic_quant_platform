"""add paper_trading_runs

Revision ID: 0001_paper_trading_runs
Revises:
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_paper_trading_runs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_trading_runs",
        sa.Column("id", sa.String(length=48), primary_key=True),
        sa.Column("task_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("run_name", sa.String(length=240), nullable=False, server_default="paper-adhoc"),
        sa.Column("strategy_id", sa.String(length=120), nullable=True, index=True),
        sa.Column("brokerage", sa.String(length=40), nullable=False, server_default="sim"),
        sa.Column("feed", sa.String(length=40), nullable=False, server_default="replay"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending", index=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
        sa.Column("initial_cash", sa.Float(), nullable=True),
        sa.Column("final_equity", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("bars_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders_submitted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fills", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("state", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_paper_trading_runs_started_at",
        "paper_trading_runs",
        ["started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_trading_runs_started_at", table_name="paper_trading_runs")
    op.drop_table("paper_trading_runs")
