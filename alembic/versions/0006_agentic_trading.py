"""agentic trading: agent_decisions, debate_turns, agent_backtests + crew_runs extensions

Revision ID: 0006_agentic_trading
Revises: 0005_flink_trading_schema
Create Date: 2026-04-23

Adds persistence for the TradingAgents-style trader crew:

- ``agent_decisions`` — one structured decision per (symbol, timestamp)
  produced by the trader crew and read back by ``AgenticAlpha``.
- ``debate_turns`` — captured Bull/Bear debate utterances so the
  Backtest Lab can show the full reasoning chain.
- ``agent_backtests`` — sidecar per ``BacktestRun`` capturing LLM
  metadata (provider, models, max debate rounds, total USD cost,
  decision cache URI).
- ``crew_runs.crew_type`` and ``crew_runs.cost_usd`` — split trader
  runs from the existing research runs and surface aggregate cost.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_agentic_trading"
down_revision = "0005_flink_trading_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crew_runs",
        sa.Column(
            "crew_type",
            sa.String(length=32),
            nullable=False,
            server_default="research",
        ),
    )
    op.add_column(
        "crew_runs",
        sa.Column(
            "cost_usd",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )
    op.create_index(
        "ix_crew_runs_crew_type",
        "crew_runs",
        ["crew_type"],
    )

    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("backtest_id", sa.String(length=36), sa.ForeignKey("backtest_runs.id"), nullable=True),
        sa.Column("strategy_id", sa.String(length=36), sa.ForeignKey("strategies.id"), nullable=True),
        sa.Column("crew_run_id", sa.String(length=36), sa.ForeignKey("crew_runs.id"), nullable=True),
        sa.Column("vt_symbol", sa.String(length=40), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False, server_default="HOLD"),
        sa.Column("size_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("rating", sa.String(length=16), nullable=False, server_default="hold"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("deep_model", sa.String(length=120), nullable=True),
        sa.Column("quick_model", sa.String(length=120), nullable=True),
        sa.Column("token_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("context_hash", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_decisions_backtest_id",
        "agent_decisions",
        ["backtest_id"],
    )
    op.create_index(
        "ix_agent_decisions_strategy_id",
        "agent_decisions",
        ["strategy_id"],
    )
    op.create_index(
        "ix_agent_decisions_crew_run_id",
        "agent_decisions",
        ["crew_run_id"],
    )
    op.create_index(
        "ix_agent_decisions_vt_symbol",
        "agent_decisions",
        ["vt_symbol"],
    )
    op.create_index(
        "ix_agent_decisions_ts",
        "agent_decisions",
        ["ts"],
    )
    op.create_index(
        "ix_agent_decisions_context_hash",
        "agent_decisions",
        ["context_hash"],
    )
    op.create_index(
        "ix_agent_decisions_created_at",
        "agent_decisions",
        ["created_at"],
    )
    op.create_index(
        "ix_agent_decisions_symbol_ts",
        "agent_decisions",
        ["vt_symbol", "ts"],
    )
    op.create_index(
        "ix_agent_decisions_backtest_ts",
        "agent_decisions",
        ["backtest_id", "ts"],
    )

    op.create_table(
        "debate_turns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "crew_run_id",
            sa.String(length=36),
            sa.ForeignKey("crew_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "decision_id",
            sa.String(length=36),
            sa.ForeignKey("agent_decisions.id"),
            nullable=True,
        ),
        sa.Column("round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("argument", sa.Text(), nullable=False),
        sa.Column("cites", sa.JSON(), nullable=True),
        sa.Column("token_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_debate_turns_crew_run_id",
        "debate_turns",
        ["crew_run_id"],
    )
    op.create_index(
        "ix_debate_turns_decision_id",
        "debate_turns",
        ["decision_id"],
    )
    op.create_index(
        "ix_debate_turns_crew_round",
        "debate_turns",
        ["crew_run_id", "round"],
    )

    op.create_table(
        "agent_backtests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "backtest_id",
            sa.String(length=36),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="precompute"),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("deep_model", sa.String(length=120), nullable=True),
        sa.Column("quick_model", sa.String(length=120), nullable=True),
        sa.Column("max_debate_rounds", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("n_decisions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_debate_turns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_token_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("decision_cache_uri", sa.String(length=512), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_backtests_backtest_id",
        "agent_backtests",
        ["backtest_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_backtests_backtest_id", "agent_backtests")
    op.drop_table("agent_backtests")

    op.drop_index("ix_debate_turns_crew_round", "debate_turns")
    op.drop_index("ix_debate_turns_decision_id", "debate_turns")
    op.drop_index("ix_debate_turns_crew_run_id", "debate_turns")
    op.drop_table("debate_turns")

    op.drop_index("ix_agent_decisions_backtest_ts", "agent_decisions")
    op.drop_index("ix_agent_decisions_symbol_ts", "agent_decisions")
    op.drop_index("ix_agent_decisions_created_at", "agent_decisions")
    op.drop_index("ix_agent_decisions_context_hash", "agent_decisions")
    op.drop_index("ix_agent_decisions_ts", "agent_decisions")
    op.drop_index("ix_agent_decisions_vt_symbol", "agent_decisions")
    op.drop_index("ix_agent_decisions_crew_run_id", "agent_decisions")
    op.drop_index("ix_agent_decisions_strategy_id", "agent_decisions")
    op.drop_index("ix_agent_decisions_backtest_id", "agent_decisions")
    op.drop_table("agent_decisions")

    op.drop_index("ix_crew_runs_crew_type", "crew_runs")
    op.drop_column("crew_runs", "cost_usd")
    op.drop_column("crew_runs", "crew_type")
