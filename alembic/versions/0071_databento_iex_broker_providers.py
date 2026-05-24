"""Broker provider catalog expansion (Phase 1, plan section 5).

Revision ID: 0071_databento_iex_broker_providers
Revises: 0070_airbyte_workspace_per_team
Create Date: 2026-05-24

The set of acceptable values for ``broker_credentials.provider`` is
a Postgres-side ``CHECK`` constraint (added in 0065) keyed off the
:data:`aqp.persistence.models_broker.KNOWN_BROKER_PROVIDERS` literal.
Phase 1 extends that literal with seven data-vendor BYOK additions
(``databento``, ``tiingo``, ``alpha_vantage``, ``quandl``,
``coingecko``, ``fred``) — the SQL constraint needs to be relaxed
to match.

The downgrade restores the pre-Phase-1 set; rows in
``broker_credentials`` with the new providers are NOT deleted on
downgrade (the platform operator owns retention).

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

from alembic import op

revision = "0071_databento_iex_broker_providers"
down_revision = "0070_airbyte_workspace_per_team"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    # Drop the pre-Phase-1 CHECK constraint if it exists; the post-
    # 0065 schema didn't always enforce one (operators that ran 0065
    # against SQLite-tests skipped it), so DROP IF EXISTS is safe.
    op.execute(
        "ALTER TABLE broker_credentials "
        "DROP CONSTRAINT IF EXISTS ck_broker_credentials_provider;"
    )
    op.execute(
        """
        ALTER TABLE broker_credentials
        ADD CONSTRAINT ck_broker_credentials_provider
        CHECK (provider IN (
            'alpaca','interactive_brokers','tradier','tradestation',
            'polygon','iex_cloud','schwab','etrade','binance','coinbase',
            'bybit','okx','kraken','tradovate','ftx','custom',
            'databento','tiingo','alpha_vantage','quandl','coingecko','fred'
        ));
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute(
        "ALTER TABLE broker_credentials "
        "DROP CONSTRAINT IF EXISTS ck_broker_credentials_provider;"
    )
    op.execute(
        """
        ALTER TABLE broker_credentials
        ADD CONSTRAINT ck_broker_credentials_provider
        CHECK (provider IN (
            'alpaca','interactive_brokers','tradier','tradestation',
            'polygon','iex_cloud','schwab','etrade','binance','coinbase',
            'bybit','okx','kraken','tradovate','ftx','custom'
        ));
        """
    )
