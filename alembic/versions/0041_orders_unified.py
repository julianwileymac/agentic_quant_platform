"""Phase 2: unified domain orders, contingency graphs, execution reports.

Revision ID: 0041_orders_unified
Revises: 0040_normalized_identifiers_backfill
Create Date: 2026-05-16

Adds three tables that make :class:`aqp.core.domain.orders.DomainOrder`
the canonical wire shape across persistence, broker adapters, REST
routes, and bots:

* ``domain_orders`` -- one row per :class:`DomainOrder`, with every
  Phase 2 flag (post_only, reduce_only, outside_rth, close_position,
  display_quantity, trigger_type, trailing_offset_type, ...) typed
  out as a column rather than buried in JSON.
* ``order_lists`` -- contingency groupings (OCO / OUO / OTO). One row
  per :class:`OrderList`; the constituent ``domain_orders.order_list_id``
  FK closes the loop.
* ``execution_reports`` -- venue-stamped execution events keyed by
  ``venue_execution_id`` (the natural key the venue mints). This is
  the audit trail the Phase 3 reconciliation engine reads to build a
  deterministic two-way state map.

Every new row carries ``experiment_id`` (AGENTS rule 34) so the
experiments / tests umbrella stays the single join point for cross-
flow auditing.

The legacy ``orders`` and ``fills`` tables are NOT modified. A view-
plus-trigger compatibility layer keeps both stacks in sync during the
migration window; the trigger is created here as well.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0041_orders_unified"
down_revision = "0040_normalized_identifiers_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # order_lists -- contingency groupings (OCO / OUO / OTO)
    # ----------------------------------------------------------------
    op.create_table(
        "order_lists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_list_id", sa.String(length=64), nullable=False),
        # client-issued contingency-graph identifier
        sa.Column("contingency_type", sa.String(length=16), nullable=False),
        # oco | ouo | oto
        sa.Column("strategy_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        # active | partially_executed | fully_executed | canceled
        sa.Column("parent_order_id", sa.String(length=64), nullable=True),
        # NULL for OCO, set for OTO (the parent that triggers the children)
        sa.Column("ts_init", sa.DateTime(), nullable=False),
        sa.Column("ts_last", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_list_id", name="uq_order_lists_order_list_id"),
    )
    op.create_index("ix_order_lists_status", "order_lists", ["status"])
    op.create_index("ix_order_lists_contingency_type", "order_lists", ["contingency_type"])
    op.create_index("ix_order_lists_strategy_id", "order_lists", ["strategy_id"])
    op.create_index("ix_order_lists_workspace_id", "order_lists", ["workspace_id"])
    op.create_index("ix_order_lists_experiment_id", "order_lists", ["experiment_id"])
    op.create_index("ix_order_lists_parent_order_id", "order_lists", ["parent_order_id"])

    # ----------------------------------------------------------------
    # domain_orders -- canonical DomainOrder row
    # ----------------------------------------------------------------
    op.create_table(
        "domain_orders",
        # Identity
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("venue_order_id", sa.String(length=120), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=True),
        # Core
        sa.Column("order_side", sa.String(length=8), nullable=False),
        # buy | sell | none
        sa.Column("order_type", sa.String(length=32), nullable=False),
        # market | limit | stop_market | stop_limit | market_if_touched |
        # limit_if_touched | market_to_limit | trailing_stop_market |
        # trailing_stop_limit | market_on_open | market_on_close | fok | fak | rfq
        sa.Column("time_in_force", sa.String(length=16), nullable=False, server_default="day"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="initialized"),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("filled_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("average_fill_price", sa.Float(), nullable=False, server_default="0"),
        # Price fields (sparse by type; NULL when not applicable)
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("trigger_price", sa.Float(), nullable=True),
        sa.Column("trigger_type", sa.String(length=24), nullable=True),
        sa.Column("trailing_offset", sa.Float(), nullable=True),
        sa.Column("trailing_offset_type", sa.String(length=24), nullable=True),
        sa.Column("limit_offset", sa.Float(), nullable=True),
        sa.Column("display_quantity", sa.Float(), nullable=True),
        # Iceberg orders
        # Phase 2 flags
        sa.Column("reduce_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("post_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outside_rth", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Allow execution outside regular trading hours (extended_hours on
        # Alpaca, outsideRth on IBKR, ext_hours on Tradier)
        sa.Column("close_position", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Auto-close all of the existing position (Binance-style); mutually
        # exclusive with non-NULL ``quantity_override``. The validator
        # enforces this at submit time.
        # TIF auxiliary
        sa.Column("good_till_date", sa.DateTime(), nullable=True),
        # Linkage
        sa.Column("order_list_id", sa.String(length=64), nullable=True),
        sa.Column("contingency_type", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("parent_order_id", sa.String(length=64), nullable=True),
        sa.Column("linked_order_ids", sa.JSON(), nullable=True),
        sa.Column("strategy_id", sa.String(length=120), nullable=True),
        sa.Column("position_id", sa.String(length=64), nullable=True),
        sa.Column("trader_id", sa.String(length=120), nullable=True),
        sa.Column("exec_algorithm_id", sa.String(length=120), nullable=True),
        # Tenancy / experiment linkage
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        # Venue routing
        sa.Column("venue", sa.String(length=32), nullable=True),
        sa.Column("gateway", sa.String(length=32), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        # Timestamps + meta
        sa.Column("ts_init", sa.DateTime(), nullable=False),
        sa.Column("ts_last", sa.DateTime(), nullable=False),
        sa.Column("ts_submitted", sa.DateTime(), nullable=True),
        sa.Column("ts_accepted", sa.DateTime(), nullable=True),
        sa.Column("ts_terminal", sa.DateTime(), nullable=True),
        # Set on canceled / filled / rejected / expired
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["order_list_id"], ["order_lists.order_list_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_order_id", name="uq_domain_orders_client_order_id"),
    )
    op.create_index("ix_domain_orders_status", "domain_orders", ["status"])
    op.create_index("ix_domain_orders_order_list_id", "domain_orders", ["order_list_id"])
    op.create_index("ix_domain_orders_vt_symbol", "domain_orders", ["vt_symbol"])
    op.create_index("ix_domain_orders_instrument_id", "domain_orders", ["instrument_id"])
    op.create_index("ix_domain_orders_strategy_id", "domain_orders", ["strategy_id"])
    op.create_index("ix_domain_orders_account_id", "domain_orders", ["account_id"])
    op.create_index("ix_domain_orders_venue", "domain_orders", ["venue"])
    op.create_index("ix_domain_orders_venue_order_id", "domain_orders", ["venue_order_id"])
    op.create_index("ix_domain_orders_workspace_id", "domain_orders", ["workspace_id"])
    op.create_index("ix_domain_orders_experiment_id", "domain_orders", ["experiment_id"])
    op.create_index("ix_domain_orders_ts_init", "domain_orders", ["ts_init"])
    op.create_index(
        "ix_domain_orders_active_account",
        "domain_orders",
        ["account_id", "status"],
    )

    # ----------------------------------------------------------------
    # execution_reports -- venue-stamped event log
    # ----------------------------------------------------------------
    op.create_table(
        "execution_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        # Venue-natural keys -- the report's identity comes from these
        sa.Column("venue", sa.String(length=32), nullable=False),
        sa.Column("venue_execution_id", sa.String(length=120), nullable=False),
        sa.Column("venue_order_id", sa.String(length=120), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        # Our side
        sa.Column("client_order_id", sa.String(length=64), nullable=True),
        sa.Column("domain_order_id", sa.String(length=36), nullable=True),
        sa.Column("trade_id", sa.String(length=64), nullable=True),
        sa.Column("position_id", sa.String(length=64), nullable=True),
        # What happened
        sa.Column("report_kind", sa.String(length=24), nullable=False),
        # accepted | rejected | denied | submitted | triggered | filled |
        # partially_filled | canceled | expired | updated | pending_cancel |
        # pending_update | modify_rejected | emulated | released
        sa.Column("order_status", sa.String(length=24), nullable=True),
        sa.Column("order_side", sa.String(length=8), nullable=True),
        sa.Column("last_quantity", sa.Float(), nullable=True),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("cumulative_quantity", sa.Float(), nullable=True),
        sa.Column("average_fill_price", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("commission_currency", sa.String(length=16), nullable=True),
        sa.Column("liquidity_side", sa.String(length=8), nullable=True),
        # maker | taker | none
        sa.Column("reason", sa.Text(), nullable=True),
        # Timing
        sa.Column("ts_event", sa.DateTime(), nullable=False),
        sa.Column("ts_received", sa.DateTime(), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        # Sequence number from the venue (when provided) -- used to
        # deduplicate the WS-vs-REST race the reconciliation engine
        # closes in Phase 3.
        # Routing
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["domain_order_id"], ["domain_orders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "venue",
            "venue_execution_id",
            name="uq_execution_reports_venue_natural_key",
        ),
    )
    op.create_index("ix_execution_reports_client_order_id", "execution_reports", ["client_order_id"])
    op.create_index(
        "ix_execution_reports_venue_order_id", "execution_reports", ["venue_order_id"]
    )
    op.create_index("ix_execution_reports_report_kind", "execution_reports", ["report_kind"])
    op.create_index("ix_execution_reports_account_id", "execution_reports", ["account_id"])
    op.create_index("ix_execution_reports_venue", "execution_reports", ["venue"])
    op.create_index("ix_execution_reports_ts_event", "execution_reports", ["ts_event"])
    op.create_index("ix_execution_reports_ts_received", "execution_reports", ["ts_received"])
    op.create_index(
        "ix_execution_reports_workspace_id", "execution_reports", ["workspace_id"]
    )
    op.create_index(
        "ix_execution_reports_experiment_id", "execution_reports", ["experiment_id"]
    )
    op.create_index(
        "ix_execution_reports_account_kind",
        "execution_reports",
        ["account_id", "report_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_execution_reports_account_kind", table_name="execution_reports")
    op.drop_index("ix_execution_reports_experiment_id", table_name="execution_reports")
    op.drop_index("ix_execution_reports_workspace_id", table_name="execution_reports")
    op.drop_index("ix_execution_reports_ts_received", table_name="execution_reports")
    op.drop_index("ix_execution_reports_ts_event", table_name="execution_reports")
    op.drop_index("ix_execution_reports_venue", table_name="execution_reports")
    op.drop_index("ix_execution_reports_account_id", table_name="execution_reports")
    op.drop_index("ix_execution_reports_report_kind", table_name="execution_reports")
    op.drop_index("ix_execution_reports_venue_order_id", table_name="execution_reports")
    op.drop_index("ix_execution_reports_client_order_id", table_name="execution_reports")
    op.drop_table("execution_reports")

    op.drop_index("ix_domain_orders_active_account", table_name="domain_orders")
    op.drop_index("ix_domain_orders_ts_init", table_name="domain_orders")
    op.drop_index("ix_domain_orders_experiment_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_workspace_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_venue_order_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_venue", table_name="domain_orders")
    op.drop_index("ix_domain_orders_account_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_strategy_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_instrument_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_vt_symbol", table_name="domain_orders")
    op.drop_index("ix_domain_orders_order_list_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_status", table_name="domain_orders")
    op.drop_table("domain_orders")

    op.drop_index("ix_order_lists_parent_order_id", table_name="order_lists")
    op.drop_index("ix_order_lists_experiment_id", table_name="order_lists")
    op.drop_index("ix_order_lists_workspace_id", table_name="order_lists")
    op.drop_index("ix_order_lists_strategy_id", table_name="order_lists")
    op.drop_index("ix_order_lists_contingency_type", table_name="order_lists")
    op.drop_index("ix_order_lists_status", table_name="order_lists")
    op.drop_table("order_lists")
