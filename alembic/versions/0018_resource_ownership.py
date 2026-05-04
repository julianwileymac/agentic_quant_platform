"""Resource ownership backfill: add owner_user_id / workspace_id /
project_id / lab_id FKs to every user-created table and seed legacy rows
with the canonical ``default-*`` IDs from migration 0017.

Revision ID: 0018_resource_ownership
Revises: 0017_tenancy_foundation
Create Date: 2026-05-03

This is the bulk migration that brings every legacy resource under the
new tenancy model. Tables fall into three buckets:

- **TENANT_OWNED**: owner_user_id + workspace_id only (sessions, chat
  messages — workspace-scoped without a project/lab).
- **PROJECT_SCOPED**: + project_id (every trading-bot artifact: strategies,
  backtests, agents, models, datasets, pipelines).
- **LAB_SCOPED**: + lab_id (RAG corpora, memory episodes, entity
  annotations — interactive-research artifacts).

Two dbt tables (``dbt_model_versions``, ``dbt_source_mappings``,
``dbt_runs``) get only TENANT_OWNED to avoid the column-name collision
with the existing ``project_id`` FK that points at ``dbt_projects``.

Reference data tables (instruments, issuers, fundamentals, news, macro,
regulatory, ownership-data, taxonomy, entity registry) stay shared and
gain no ownership columns — they're shared crosswalks not user output.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_resource_ownership"
down_revision = "0017_tenancy_foundation"
branch_labels = None
depends_on = None


# Mirror of aqp.config.defaults — see migration 0017 for the seed.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"
DEFAULT_LAB_ID = "00000000-0000-0000-0000-000000000006"


# Tables that get owner_user_id + workspace_id only (no project/lab scope).
TENANT_OWNED = (
    "sessions",
    "chat_messages",
    # dbt secondary tables — they already have a project_id FK pointing
    # at dbt_projects, so the tenancy project_id column would collide.
    "dbt_model_versions",
    "dbt_source_mappings",
    "dbt_runs",
)


# Tables that get owner_user_id + workspace_id + project_id (trading-bot
# artifacts).
PROJECT_SCOPED = (
    "strategies",
    "strategy_versions",
    "strategy_tests",
    "backtest_runs",
    "signals",
    "orders",
    "fills",
    "ledger_entries",
    "optimization_runs",
    "optimization_trials",
    "paper_trading_runs",
    "crew_runs",
    "agent_runs",
    "agent_specs",
    "agent_spec_versions",
    "agent_runs_v2",
    "agent_run_steps",
    "agent_run_artifacts",
    "agent_evaluations",
    "agent_eval_metrics",
    "agent_decisions",
    "debate_turns",
    "agent_backtests",
    "agent_judge_reports",
    "agent_replay_runs",
    "backtest_interrupts",
    "model_versions",
    "model_deployments",
    "rl_episodes",
    "feature_sets",
    "feature_set_versions",
    "feature_set_usages",
    "equity_reports",
    "dataset_catalogs",
    "dataset_versions",
    "split_plans",
    "split_artifacts",
    "pipeline_recipes",
    "experiment_plans",
    "dataset_presets",
    "extraction_audit",
    "pipeline_manifests",
    "pipeline_runs",
    "dataset_profiles",
    "fetcher_runs",
    "datahub_sync_log",
    "airbyte_connectors",
    "airbyte_connections",
    "airbyte_sync_runs",
    "dbt_projects",
)


# Tables that get owner_user_id + workspace_id + lab_id (interactive-
# research artifacts).
LAB_SCOPED = (
    "agent_annotations",
    "rag_corpora",
    "rag_documents",
    "rag_chunks",
    "rag_summaries",
    "rag_queries",
    "rag_eval_runs",
    "memory_episodes",
    "memory_reflections",
    "memory_outcomes",
    "entity_annotations",
)


def _add_tenant_columns(table: str) -> None:
    """Add owner_user_id + workspace_id with default backfill."""
    try:
        op.add_column(
            table,
            sa.Column(
                "owner_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
                server_default=DEFAULT_USER_ID,
            ),
        )
        op.create_index(f"ix_{table}_owner_user_id", table, ["owner_user_id"])
    except Exception:  # pragma: no cover - re-run safety
        pass
    try:
        op.add_column(
            table,
            sa.Column(
                "workspace_id",
                sa.String(length=36),
                sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
                nullable=True,
                server_default=DEFAULT_WORKSPACE_ID,
            ),
        )
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
    except Exception:
        pass


def _add_project_column(table: str) -> None:
    try:
        op.add_column(
            table,
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
                server_default=DEFAULT_PROJECT_ID,
            ),
        )
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])
    except Exception:
        pass


def _add_lab_column(table: str) -> None:
    try:
        op.add_column(
            table,
            sa.Column(
                "lab_id",
                sa.String(length=36),
                sa.ForeignKey("labs.id", ondelete="SET NULL"),
                nullable=True,
                server_default=DEFAULT_LAB_ID,
            ),
        )
        op.create_index(f"ix_{table}_lab_id", table, ["lab_id"])
    except Exception:
        pass


def _backfill_table(table: str, *, with_project: bool, with_lab: bool) -> None:
    """Stamp every existing row with the default-* IDs."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"UPDATE {table} SET owner_user_id = :u WHERE owner_user_id IS NULL"
        ),
        {"u": DEFAULT_USER_ID},
    )
    bind.execute(
        sa.text(
            f"UPDATE {table} SET workspace_id = :w WHERE workspace_id IS NULL"
        ),
        {"w": DEFAULT_WORKSPACE_ID},
    )
    if with_project:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET project_id = :p WHERE project_id IS NULL"
            ),
            {"p": DEFAULT_PROJECT_ID},
        )
    if with_lab:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET lab_id = :l WHERE lab_id IS NULL"
            ),
            {"l": DEFAULT_LAB_ID},
        )


def upgrade() -> None:
    for table in TENANT_OWNED:
        _add_tenant_columns(table)
        _backfill_table(table, with_project=False, with_lab=False)

    for table in PROJECT_SCOPED:
        _add_tenant_columns(table)
        _add_project_column(table)
        _backfill_table(table, with_project=True, with_lab=False)

    for table in LAB_SCOPED:
        _add_tenant_columns(table)
        _add_lab_column(table)
        _backfill_table(table, with_project=False, with_lab=True)


def _drop_columns(table: str, cols: tuple[str, ...]) -> None:
    for col in cols:
        try:
            op.drop_index(f"ix_{table}_{col}", table_name=table)
        except Exception:
            pass
        try:
            op.drop_column(table, col)
        except Exception:
            pass


def downgrade() -> None:
    for table in TENANT_OWNED:
        _drop_columns(table, ("workspace_id", "owner_user_id"))
    for table in PROJECT_SCOPED:
        _drop_columns(table, ("project_id", "workspace_id", "owner_user_id"))
    for table in LAB_SCOPED:
        _drop_columns(table, ("lab_id", "workspace_id", "owner_user_id"))
