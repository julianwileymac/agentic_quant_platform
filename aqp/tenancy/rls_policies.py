"""Registry of RLS-eligible tables + their canonical policies (Workstream F).

The plan ships RLS on every table that carries the
:class:`TenantOwnedMixin` columns (``owner_user_id`` /
``workspace_id``). For each table we install:

- ``ALTER TABLE ... ENABLE ROW LEVEL SECURITY;``
- ``ALTER TABLE ... FORCE ROW LEVEL SECURITY;`` (so even table owners
  obey the policies).
- ``CREATE POLICY tenant_isolation_<table>`` with the predicate the
  registry below specifies.

Predicates use ``current_setting('app.current_organization_id', true)``
and ``current_setting('app.current_workspace_id', true)`` GUCs which
:class:`SharedSchemaRLSStrategy` sets via ``SET LOCAL`` at session
checkout. The ``true`` second arg makes ``current_setting`` return
``NULL`` rather than raising when the GUC is absent — required for
migrations and admin/maintenance jobs running as the BYPASSRLS
``app_migrator`` role.

The ``public_data`` schema is the explicit cross-tenant carve-out:
tables in that schema get a permissive ``USING (true)`` policy so
public datasets (GDELT, exchange OHLCV) remain readable.

The full DDL bundle is materialised by the
``alembic/versions/0063_tenancy_strategy.py`` migration (workstream
F.1). New tenant-scoped tables added in future migrations SHOULD add
themselves to ``RLS_TABLES`` and ship a one-line migration extending
the policy set.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RlsTable:
    """Description of one RLS-eligible table.

    ``predicate_template`` accepts the table name as a positional
    format arg (``{table}``) so migrations can re-use the same template
    string for the policy DDL.
    """

    name: str
    workspace_predicate: bool = True  # scope at workspace level by default
    organization_predicate: bool = False  # scope at organization level (optional)
    has_workspace_column: bool = True


# Tables protected by the workspace-scoped policy. Every row in these
# tables carries a ``workspace_id`` FK (TenantOwnedMixin) and an
# ``owner_user_id``; the RLS predicate matches the session GUC against
# ``workspace_id``.
RLS_TABLES: tuple[RlsTable, ...] = (
    # Strategy + bot + RL artefacts
    RlsTable(name="backtest_runs"),
    RlsTable(name="bot_deployments"),
    RlsTable(name="strategy_tests"),
    RlsTable(name="paper_trading_runs"),
    RlsTable(name="agent_runs_v2"),
    RlsTable(name="agent_runs"),
    RlsTable(name="ml_experiment_runs"),
    RlsTable(name="ml_alpha_backtest_runs"),
    RlsTable(name="rl_runs"),
    RlsTable(name="analysis_runs"),
    RlsTable(name="analysis_step_results"),
    # Spec tables
    RlsTable(name="agent_specs"),
    RlsTable(name="bots"),
    RlsTable(name="rl_experiment_specs"),
    RlsTable(name="analysis_specs"),
    # Datasets + lineage
    RlsTable(name="dataset_catalogs"),
    RlsTable(name="data_lineage_events"),
    RlsTable(name="lineage_dataset_vertex"),
    RlsTable(name="lineage_transform_vertex"),
    RlsTable(name="lineage_edge"),
    # Workflow / orchestration / terraform
    RlsTable(name="workflow_runs"),
    RlsTable(name="terraform_runs"),
    RlsTable(name="workload_runs"),
    RlsTable(name="assistant_runs"),
    # Other run / artefact tables
    RlsTable(name="agent_replay_runs"),
    RlsTable(name="crew_runs"),
    RlsTable(name="optimization_runs"),
    RlsTable(name="pipeline_runs"),
    RlsTable(name="fetcher_runs"),
    RlsTable(name="lab_runs"),
    RlsTable(name="lab_node_runs"),
    RlsTable(name="rag_eval_runs"),
)


def policy_ddl(table: RlsTable) -> str:
    """Return the ``CREATE POLICY`` DDL for one RLS-eligible table.

    Uses ``IS NOT DISTINCT FROM`` so rows with a NULL ``workspace_id``
    are treated as "unscoped" (legacy + reference data) and remain
    readable across all tenants — matches today's application-layer
    behaviour where ``filter_resources_for_user`` accepts ``NULL``
    rows as cross-tenant defaults.
    """
    predicate = (
        f"workspace_id IS NULL "
        f"OR workspace_id = current_setting('app.current_workspace_id', true)"
    )
    return (
        f"CREATE POLICY tenant_isolation_{table.name} ON {table.name} "
        f"USING ({predicate});"
    )


def enable_rls_ddl(table: RlsTable) -> str:
    """Return the ``ENABLE`` + ``FORCE`` DDL for ``table.name``."""
    return (
        f"ALTER TABLE {table.name} ENABLE ROW LEVEL SECURITY; "
        f"ALTER TABLE {table.name} FORCE ROW LEVEL SECURITY;"
    )


def disable_rls_ddl(table: RlsTable) -> str:
    """Inverse of :func:`enable_rls_ddl` — used in migration downgrade."""
    return (
        f"DROP POLICY IF EXISTS tenant_isolation_{table.name} ON {table.name}; "
        f"ALTER TABLE {table.name} NO FORCE ROW LEVEL SECURITY; "
        f"ALTER TABLE {table.name} DISABLE ROW LEVEL SECURITY;"
    )


__all__ = [
    "RLS_TABLES",
    "RlsTable",
    "disable_rls_ddl",
    "enable_rls_ddl",
    "policy_ddl",
]
