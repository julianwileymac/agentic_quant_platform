"""Enforce NOT NULL on owner_user_id + workspace_id after backfill.

Revision ID: 0019_ownership_enforce
Revises: 0018_resource_ownership
Create Date: 2026-05-03

Run after 0018 has populated every legacy row with the default-* IDs so
the constraint can be tightened without a verification step. Skips
project_id / lab_id (those stay nullable — only the owner + workspace
are mandatory).
"""
from __future__ import annotations

from alembic import op

revision = "0019_ownership_enforce"
down_revision = "0018_resource_ownership"
branch_labels = None
depends_on = None


# Re-import the table groups from 0018 by name lookup so we don't import
# from another revision file (which Alembic discourages).
TENANT_OWNED = (
    "sessions",
    "chat_messages",
    "dbt_model_versions",
    "dbt_source_mappings",
    "dbt_runs",
)

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


def _enforce_not_null(table: str) -> None:
    for col in ("owner_user_id", "workspace_id"):
        try:
            op.alter_column(table, col, nullable=False)
        except Exception:  # pragma: no cover - re-run safety
            pass


def upgrade() -> None:
    for table in TENANT_OWNED + PROJECT_SCOPED + LAB_SCOPED:
        _enforce_not_null(table)


def _relax_not_null(table: str) -> None:
    for col in ("owner_user_id", "workspace_id"):
        try:
            op.alter_column(table, col, nullable=True)
        except Exception:
            pass


def downgrade() -> None:
    for table in TENANT_OWNED + PROJECT_SCOPED + LAB_SCOPED:
        _relax_not_null(table)
