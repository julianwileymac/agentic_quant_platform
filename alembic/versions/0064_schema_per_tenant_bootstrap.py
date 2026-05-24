"""tenant_template + public_data schemas for schema-per-tenant strategy.

Revision ID: 0064_schema_per_tenant_bootstrap
Revises: 0063_tenancy_strategy
Create Date: 2026-05-24

Workstream F.2 of the AQP Data Layer Selective Additive Enhancement.

Creates two cross-tenant schemas on PostgreSQL deployments:

- ``tenant_template`` — empty source schema cloned by
  :meth:`SchemaPerTenantStrategy.onboard` when a new mid-tier B2B
  tenant lands. The schema gets populated by replaying the public
  application schema's DDL as part of the onboarding workflow; this
  migration just ensures the schema container exists.
- ``public_data`` — cross-tenant readable schema for public datasets
  (GDELT, exchange OHLCV, etc.). The shared-schema RLS policy lets
  ``workspace_id IS NULL`` rows through, but readers that want
  *strong* "no tenant filter" semantics should land tables in
  ``public_data`` instead.

Both schemas are SQLite-incompatible. The migration is a no-op on
SQLite.

AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

from alembic import op

revision = "0064_schema_per_tenant_bootstrap"
down_revision = "0063_tenancy_strategy"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    op.execute("CREATE SCHEMA IF NOT EXISTS tenant_template")
    op.execute("CREATE SCHEMA IF NOT EXISTS public_data")
    # Grant the app_runtime + app_migrator roles usage on the
    # template + public_data schemas so the strategies can issue
    # ``search_path`` writes against them.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                EXECUTE 'GRANT USAGE ON SCHEMA tenant_template TO app_runtime';
                EXECUTE 'GRANT USAGE ON SCHEMA public_data TO app_runtime';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_migrator') THEN
                EXECUTE 'GRANT USAGE, CREATE ON SCHEMA tenant_template TO app_migrator';
                EXECUTE 'GRANT USAGE, CREATE ON SCHEMA public_data TO app_migrator';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute("DROP SCHEMA IF EXISTS public_data CASCADE")
    op.execute("DROP SCHEMA IF EXISTS tenant_template CASCADE")
