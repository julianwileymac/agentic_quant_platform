"""Verify the tenancy mixins decorate every user-created table.

The mixins live in :mod:`aqp.persistence._tenancy_mixins` and are applied
to every model class that gets backfilled by migration 0018. These tests
introspect the SQLAlchemy metadata to confirm the columns are present.
"""
from __future__ import annotations

import pytest

# Force-register every model so Base.metadata is populated.
from aqp.persistence import (  # noqa: F401
    models,
    models_agents,
    models_airbyte,
    models_dbt,
    models_entity_registry,
    models_extraction,
    models_memory,
    models_pipelines,
    models_rag,
    models_tenancy,
)
from aqp.persistence.models import Base

PROJECT_SCOPED_TABLES = {
    "strategies",
    "strategy_versions",
    "backtest_runs",
    "signals",
    "orders",
    "fills",
    "ledger_entries",
    "optimization_runs",
    "paper_trading_runs",
    "crew_runs",
    "agent_runs",
    "agent_specs",
    "agent_spec_versions",
    "agent_runs_v2",
    "agent_run_steps",
    "agent_run_artifacts",
    "agent_evaluations",
    "agent_decisions",
    "model_versions",
    "model_deployments",
    "feature_sets",
    "equity_reports",
    "dataset_catalogs",
    "dataset_versions",
    "pipeline_manifests",
    "pipeline_runs",
    "fetcher_runs",
    "airbyte_connectors",
    "airbyte_connections",
    "dbt_projects",
    "dataset_presets",
}

LAB_SCOPED_TABLES = {
    "rag_corpora",
    "rag_documents",
    "rag_summaries",
    "rag_queries",
    "memory_episodes",
    "memory_reflections",
    "memory_outcomes",
    "agent_annotations",
    "entity_annotations",
}

TENANT_ONLY_TABLES = {
    "sessions",
    "chat_messages",
    "dbt_model_versions",
    "dbt_source_mappings",
    "dbt_runs",
}

SHARED_TABLES = {
    "instruments",
    "data_sources",
    "issuers",
    "fred_series",
    "sec_filings",
    "gdelt_mentions",
    "entities",
}


def _table(name: str):
    return Base.metadata.tables.get(name)


@pytest.mark.parametrize("table_name", sorted(PROJECT_SCOPED_TABLES | LAB_SCOPED_TABLES | TENANT_ONLY_TABLES))
def test_user_created_tables_have_owner_user_id(table_name: str) -> None:
    table = _table(table_name)
    assert table is not None, f"table {table_name} not registered"
    assert "owner_user_id" in table.c, f"{table_name} missing owner_user_id"


@pytest.mark.parametrize("table_name", sorted(PROJECT_SCOPED_TABLES | LAB_SCOPED_TABLES | TENANT_ONLY_TABLES))
def test_user_created_tables_have_workspace_id(table_name: str) -> None:
    table = _table(table_name)
    assert table is not None, f"table {table_name} not registered"
    assert "workspace_id" in table.c, f"{table_name} missing workspace_id"


@pytest.mark.parametrize("table_name", sorted(PROJECT_SCOPED_TABLES))
def test_project_scoped_tables_have_project_id(table_name: str) -> None:
    table = _table(table_name)
    assert table is not None, f"table {table_name} not registered"
    assert "project_id" in table.c, f"{table_name} missing project_id"


@pytest.mark.parametrize("table_name", sorted(LAB_SCOPED_TABLES))
def test_lab_scoped_tables_have_lab_id(table_name: str) -> None:
    table = _table(table_name)
    assert table is not None, f"table {table_name} not registered"
    assert "lab_id" in table.c, f"{table_name} missing lab_id"


@pytest.mark.parametrize("table_name", sorted(SHARED_TABLES))
def test_shared_reference_tables_skip_tenancy_columns(table_name: str) -> None:
    """Reference market data should not gain ownership FKs."""
    table = _table(table_name)
    assert table is not None, f"table {table_name} not registered"
    # Shared tables should not have any of the tenancy-mixin columns.
    for tenancy_col in ("owner_user_id", "workspace_id", "project_id", "lab_id"):
        assert tenancy_col not in table.c, (
            f"shared table {table_name} should not have {tenancy_col}"
        )


def test_dbt_secondary_tables_avoid_project_id_collision() -> None:
    """``dbt_model_versions``/``dbt_source_mappings``/``dbt_runs`` keep their
    existing dbt-specific ``project_id`` column and skip the tenancy
    project_id to avoid the column-name collision.
    """
    for table_name in ("dbt_model_versions", "dbt_source_mappings", "dbt_runs"):
        table = _table(table_name)
        assert table is not None
        assert "project_id" in table.c  # The existing dbt-projects FK
        # The tenancy mixin only applied TenantOwnedMixin to these tables.
        # The project_id column is the legacy one, not the tenancy one — we
        # can't easily distinguish, but the FK target is dbt_projects.
        fk_targets = {fk.column.table.name for fk in table.c.project_id.foreign_keys}
        assert fk_targets == {"dbt_projects"}, (
            f"{table_name}.project_id should still point at dbt_projects, got {fk_targets}"
        )
