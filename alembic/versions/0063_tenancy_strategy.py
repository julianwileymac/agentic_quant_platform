"""Multi-tenant TenancyStrategy: organizations columns + RLS DDL.

Revision ID: 0063_tenancy_strategy
Revises: 0060_openlineage_outbox
Create Date: 2026-05-24

Workstream F.1 of the AQP Data Layer Selective Additive Enhancement.

This migration adds three columns to ``organizations`` and installs
PostgreSQL Row-Level Security on every tenant-scoped table the
platform owns. The runtime stays connected as a BYPASSRLS role by
default (``settings.tenancy_rls_enforce='off'``) so existing routes
keep working; flipping the env var to ``strict`` switches the
runtime to a non-BYPASSRLS role and the RLS predicate is enforced
at the database layer.

SQLite test databases skip the RLS DDL entirely — the column
additions still apply.

AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0063_tenancy_strategy"
down_revision = "0062_user_oauth_tokens"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


_RLS_TABLES: tuple[str, ...] = (
    "backtest_runs",
    "bot_deployments",
    "strategy_tests",
    "paper_trading_runs",
    "agent_runs_v2",
    "agent_runs",
    "ml_experiment_runs",
    "ml_alpha_backtest_runs",
    "rl_runs",
    "analysis_runs",
    "analysis_step_results",
    "agent_specs",
    "bots",
    "rl_experiment_specs",
    "analysis_specs",
    "dataset_catalogs",
    "data_lineage_events",
    "lineage_dataset_vertex",
    "lineage_transform_vertex",
    "lineage_edge",
    "workflow_runs",
    "terraform_runs",
    "workload_runs",
    "assistant_runs",
    "agent_replay_runs",
    "crew_runs",
    "optimization_runs",
    "pipeline_runs",
    "fetcher_runs",
    "lab_runs",
    "lab_node_runs",
    "rag_eval_runs",
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # organizations columns
    # ------------------------------------------------------------------
    op.add_column(
        "organizations",
        sa.Column(
            "tenancy_strategy",
            sa.String(32),
            nullable=True,
            server_default="shared_schema_rls",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("tenancy_schema_name", sa.String(80), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("tenancy_dsn_vault_path", sa.String(240), nullable=True),
    )
    op.create_index(
        "ix_organizations_tenancy_strategy",
        "organizations",
        ["tenancy_strategy"],
    )

    # ------------------------------------------------------------------
    # RLS — Postgres only
    # ------------------------------------------------------------------
    if not _is_postgres():
        return

    # Roles. Idempotent CREATE so re-running on a clean DB doesn't
    # fail with "role already exists".
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                CREATE ROLE app_runtime NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_migrator') THEN
                CREATE ROLE app_migrator NOLOGIN BYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    # Enable RLS + install policy per table. Each block is wrapped in a
    # DO so a missing table (some are added by later migrations the
    # operator might be running out-of-order) downgrades to a NOTICE
    # rather than aborting the whole upgrade.
    for table in _RLS_TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = '{table}'
                ) THEN
                    EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
                    EXECUTE 'ALTER TABLE {table} FORCE ROW LEVEL SECURITY';
                    EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}';
                    EXECUTE 'CREATE POLICY tenant_isolation_{table} ON {table} '
                            'USING (workspace_id IS NULL OR workspace_id = '
                            'current_setting(''app.current_workspace_id'', true))';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_runtime';
                ELSE
                    RAISE NOTICE 'skipping RLS for missing table {table}';
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    if _is_postgres():
        for table in _RLS_TABLES:
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = '{table}'
                    ) THEN
                        EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}';
                        EXECUTE 'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY';
                        EXECUTE 'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY';
                    END IF;
                END
                $$;
                """
            )
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                    DROP ROLE app_runtime;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_migrator') THEN
                    DROP ROLE app_migrator;
                END IF;
            END
            $$;
            """
        )

    op.drop_index("ix_organizations_tenancy_strategy", table_name="organizations")
    op.drop_column("organizations", "tenancy_dsn_vault_path")
    op.drop_column("organizations", "tenancy_schema_name")
    op.drop_column("organizations", "tenancy_strategy")
