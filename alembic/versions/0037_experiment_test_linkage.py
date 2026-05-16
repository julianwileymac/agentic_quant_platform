"""Link existing typed run tables to the experiments / tests umbrella.

Revision ID: 0037_experiment_test_linkage
Revises: 0036_experiments_tests
Create Date: 2026-05-16

Adds nullable ``experiment_id`` (and ``test_id`` where it makes sense)
foreign keys to every existing run-producing table so the new
:mod:`aqp.persistence.models_experiments` umbrella has something to
join against. Existing rows stay at ``NULL`` — only new flows opt in.

AGENTS.md rule 34 (added in this rollout): every new run-producing
flow MUST populate ``experiment_id`` (and ``test_id`` where
applicable) on its run row. Don't add a new ``*_runs`` table without
an ``experiment_id`` FK.

AGENTS.md rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0037_experiment_test_linkage"
down_revision = "0036_experiments_tests"
branch_labels = None
depends_on = None


# Tables that should grow an ``experiment_id`` FK. Each entry is a
# (table_name, fk_constraint_name, idx_name) tuple. Add ``test_id``
# only on rows that represent a single assertion evaluation
# (``strategy_tests`` is the obvious one — its row IS a test result).
TABLES_WITH_EXPERIMENT_FK: tuple[tuple[str, str, str], ...] = (
    ("backtest_runs", "fk_backtest_runs_experiment_id", "ix_backtest_runs_experiment_id"),
    ("ml_experiment_runs", "fk_ml_experiment_runs_experiment_id", "ix_ml_experiment_runs_experiment_id"),
    ("rl_runs", "fk_rl_runs_experiment_id", "ix_rl_runs_experiment_id"),
    ("analysis_runs", "fk_analysis_runs_experiment_id", "ix_analysis_runs_experiment_id"),
    ("bot_deployments", "fk_bot_deployments_experiment_id", "ix_bot_deployments_experiment_id"),
    ("strategy_tests", "fk_strategy_tests_experiment_id", "ix_strategy_tests_experiment_id"),
    ("paper_trading_runs", "fk_paper_trading_runs_experiment_id", "ix_paper_trading_runs_experiment_id"),
    ("agent_runs_v2", "fk_agent_runs_v2_experiment_id", "ix_agent_runs_v2_experiment_id"),
    ("agent_runs", "fk_agent_runs_experiment_id", "ix_agent_runs_experiment_id"),
)


# Tables that should ALSO carry a ``test_id`` FK — the row represents
# a single assertion's evaluation outcome.
TABLES_WITH_TEST_FK: tuple[tuple[str, str, str], ...] = (
    ("strategy_tests", "fk_strategy_tests_test_id", "ix_strategy_tests_test_id"),
)


def upgrade() -> None:
    for table, fk_name, idx_name in TABLES_WITH_EXPERIMENT_FK:
        op.add_column(
            table,
            sa.Column("experiment_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            fk_name,
            table,
            "aqp_experiments",
            ["experiment_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(idx_name, table, ["experiment_id"])

    for table, fk_name, idx_name in TABLES_WITH_TEST_FK:
        op.add_column(
            table,
            sa.Column("test_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            fk_name,
            table,
            "aqp_tests",
            ["test_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(idx_name, table, ["test_id"])


def downgrade() -> None:
    for table, fk_name, idx_name in TABLES_WITH_TEST_FK:
        op.drop_index(idx_name, table_name=table)
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.drop_column(table, "test_id")

    for table, fk_name, idx_name in TABLES_WITH_EXPERIMENT_FK:
        op.drop_index(idx_name, table_name=table)
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.drop_column(table, "experiment_id")
