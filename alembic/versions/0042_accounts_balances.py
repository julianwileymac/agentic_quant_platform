"""Phase 3: persistent accounts + balance segregation + position rows.

Revision ID: 0042_accounts_balances
Revises: 0041_orders_unified
Create Date: 2026-05-16

Promotes the legacy in-memory :class:`aqp.core.types.AccountData`
(``cash + equity + margin_used``) into three first-class tables:

* ``accounts`` -- one row per (venue, brokerage account), with
  ``account_type`` (cash | margin | portfolio_margin | futures |
  crypto_spot | crypto_deriv) and ``oms_type`` (netting | hedging)
* ``account_balances`` -- per-currency, per-balance-kind row so we can
  segregate ``CASH`` from ``MARGIN_INITIAL`` / ``MARGIN_MAINTENANCE`` /
  ``BUYING_POWER`` / ``EXCESS_LIQUIDITY`` / ``UNREALIZED_PNL`` without
  having to overload a single ``cash`` field
* ``account_positions`` -- per-instrument, per-position-side
  (``NET`` / ``LONG`` / ``SHORT``) so hedge-mode venues can carry
  simultaneous long and short positions on the same instrument

Every new run row already carries ``experiment_id`` (AGENTS rule 34).

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0042_accounts_balances"
down_revision = "0041_orders_unified"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --------------------------------------------------------------
    # accounts
    # --------------------------------------------------------------
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=120), nullable=False),
        # Venue-natural account id (IBKR-DU12345 / Alpaca-PAPER-xxx)
        sa.Column("venue", sa.String(length=32), nullable=False),
        # alpaca | ibkr | tradier | binance | kraken | bybit | sim | ...
        sa.Column("gateway", sa.String(length=32), nullable=True),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        # cash | margin | portfolio_margin | futures | crypto_spot |
        # crypto_deriv | betting
        sa.Column("oms_type", sa.String(length=16), nullable=False, server_default="netting"),
        # netting | hedging
        sa.Column("allow_cash_positions", sa.Boolean(), nullable=False, server_default=sa.true()),
        # When True, fiat cash + spot crypto are treated as positions
        # rather than as margin collateral.
        sa.Column("base_currency", sa.String(length=16), nullable=False, server_default="USD"),
        sa.Column("nickname", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        # active | disabled | closed
        sa.Column("is_paper", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Tenancy + experiment linkage
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue", "account_id", name="uq_accounts_venue_account_id"),
    )
    op.create_index("ix_accounts_account_id", "accounts", ["account_id"])
    op.create_index("ix_accounts_venue", "accounts", ["venue"])
    op.create_index("ix_accounts_status", "accounts", ["status"])
    op.create_index("ix_accounts_is_paper", "accounts", ["is_paper"])
    op.create_index("ix_accounts_workspace_id", "accounts", ["workspace_id"])
    op.create_index("ix_accounts_owner_user_id", "accounts", ["owner_user_id"])

    # --------------------------------------------------------------
    # account_balances
    # --------------------------------------------------------------
    op.create_table(
        "account_balances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_pk", sa.String(length=36), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("balance_kind", sa.String(length=32), nullable=False),
        # CASH | MARGIN_INITIAL | MARGIN_MAINTENANCE | BUYING_POWER |
        # EXCESS_LIQUIDITY | UNREALIZED_PNL | REALIZED_PNL_DAY |
        # WITHDRAWABLE | LOCKED
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("snapshot_ts", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        # venue_rest | venue_ws | manager | sim
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["account_pk"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_pk",
            "currency",
            "balance_kind",
            name="uq_account_balances_address",
        ),
    )
    op.create_index("ix_account_balances_account_pk", "account_balances", ["account_pk"])
    op.create_index("ix_account_balances_currency", "account_balances", ["currency"])
    op.create_index(
        "ix_account_balances_balance_kind", "account_balances", ["balance_kind"]
    )

    # --------------------------------------------------------------
    # account_positions
    # --------------------------------------------------------------
    op.create_table(
        "account_positions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_pk", sa.String(length=36), nullable=False),
        sa.Column("venue", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=False),
        sa.Column("position_side", sa.String(length=8), nullable=False, server_default="net"),
        # net | long | short  (hedge mode = LONG/SHORT split; netting = NET only)
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("average_entry_price", sa.Float(), nullable=True),
        sa.Column("market_price", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("leverage", sa.Float(), nullable=True),
        sa.Column("liquidation_price", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("snapshot_ts", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["account_pk"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_pk",
            "venue",
            "vt_symbol",
            "position_side",
            name="uq_account_positions_composite_key",
        ),
    )
    op.create_index("ix_account_positions_account_pk", "account_positions", ["account_pk"])
    op.create_index("ix_account_positions_vt_symbol", "account_positions", ["vt_symbol"])
    op.create_index("ix_account_positions_venue", "account_positions", ["venue"])
    op.create_index(
        "ix_account_positions_instrument_id", "account_positions", ["instrument_id"]
    )
    op.create_index(
        "ix_account_positions_address",
        "account_positions",
        ["account_pk", "venue", "vt_symbol"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_positions_address", table_name="account_positions")
    op.drop_index("ix_account_positions_instrument_id", table_name="account_positions")
    op.drop_index("ix_account_positions_venue", table_name="account_positions")
    op.drop_index("ix_account_positions_vt_symbol", table_name="account_positions")
    op.drop_index("ix_account_positions_account_pk", table_name="account_positions")
    op.drop_table("account_positions")

    op.drop_index("ix_account_balances_balance_kind", table_name="account_balances")
    op.drop_index("ix_account_balances_currency", table_name="account_balances")
    op.drop_index("ix_account_balances_account_pk", table_name="account_balances")
    op.drop_table("account_balances")

    op.drop_index("ix_accounts_owner_user_id", table_name="accounts")
    op.drop_index("ix_accounts_workspace_id", table_name="accounts")
    op.drop_index("ix_accounts_is_paper", table_name="accounts")
    op.drop_index("ix_accounts_status", table_name="accounts")
    op.drop_index("ix_accounts_venue", table_name="accounts")
    op.drop_index("ix_accounts_account_id", table_name="accounts")
    op.drop_table("accounts")
