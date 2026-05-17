"""Persistence models for Phase 2: unified DomainOrder, OrderList, ExecutionReport.

Reflects the schema added in Alembic migration ``0041_orders_unified``.
The legacy ``orders`` / ``fills`` tables (in :mod:`aqp.persistence.models`)
remain untouched -- a compatibility shim in
:mod:`aqp.trading.execution.legacy_adapter` keeps both stacks in sync
during the migration window.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence.models import Base, _uuid


class OrderListRow(Base):
    """One contingency-graph row (OCO / OUO / OTO).

    Constituent orders carry an FK to ``order_list_id`` via
    :class:`DomainOrderRow.order_list_id` so a single-order lookup can
    discover its peers without a full table scan.
    """

    __tablename__ = "order_lists"
    id = Column(String(36), primary_key=True, default=_uuid)
    order_list_id = Column(String(64), nullable=False, unique=True)
    contingency_type = Column(String(16), nullable=False)
    # oco | ouo | oto
    strategy_id = Column(String(120), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="active", index=True)
    # active | partially_executed | fully_executed | canceled
    parent_order_id = Column(String(64), nullable=True, index=True)
    ts_init = Column(DateTime, nullable=False, default=datetime.utcnow)
    ts_last = Column(DateTime, nullable=False, default=datetime.utcnow)
    workspace_id = Column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    meta = Column(JSON, default=dict)

    __table_args__ = (
        Index("ix_order_lists_contingency_type", "contingency_type"),
    )


class DomainOrderRow(Base):
    """Canonical :class:`aqp.core.domain.orders.DomainOrder` row.

    Every Phase 2 flag is typed out as a column rather than buried in a
    JSON blob so brokers + risk checks can read them with a single
    SELECT. The polymorphic subclass tree on the in-memory side
    (MarketOrder, LimitOrder, StopMarketOrder, ...) is captured here
    by the ``order_type`` discriminator column plus the sparse-by-type
    pricing columns (price, trigger_price, trailing_offset, ...).
    """

    __tablename__ = "domain_orders"
    id = Column(String(36), primary_key=True, default=_uuid)
    client_order_id = Column(String(64), nullable=False, unique=True)
    venue_order_id = Column(String(120), nullable=True, index=True)
    vt_symbol = Column(String(64), nullable=False, index=True)
    instrument_id = Column(
        String(36),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    order_side = Column(String(8), nullable=False)
    order_type = Column(String(32), nullable=False)
    time_in_force = Column(String(16), nullable=False, default="day")
    status = Column(String(24), nullable=False, default="initialized", index=True)
    quantity = Column(Float, nullable=False)
    filled_quantity = Column(Float, nullable=False, default=0.0)
    average_fill_price = Column(Float, nullable=False, default=0.0)

    price = Column(Float, nullable=True)
    trigger_price = Column(Float, nullable=True)
    trigger_type = Column(String(24), nullable=True)
    trailing_offset = Column(Float, nullable=True)
    trailing_offset_type = Column(String(24), nullable=True)
    limit_offset = Column(Float, nullable=True)
    display_quantity = Column(Float, nullable=True)

    reduce_only = Column(Boolean, nullable=False, default=False)
    post_only = Column(Boolean, nullable=False, default=False)
    outside_rth = Column(Boolean, nullable=False, default=False)
    close_position = Column(Boolean, nullable=False, default=False)

    good_till_date = Column(DateTime, nullable=True)

    order_list_id = Column(
        String(64),
        ForeignKey("order_lists.order_list_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contingency_type = Column(String(16), nullable=False, default="none")
    parent_order_id = Column(String(64), nullable=True)
    linked_order_ids = Column(JSON, default=list)

    strategy_id = Column(String(120), nullable=True, index=True)
    position_id = Column(String(64), nullable=True)
    trader_id = Column(String(120), nullable=True)
    exec_algorithm_id = Column(String(120), nullable=True)

    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    venue = Column(String(32), nullable=True, index=True)
    gateway = Column(String(32), nullable=True)
    account_id = Column(String(64), nullable=True, index=True)

    ts_init = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    ts_last = Column(DateTime, nullable=False, default=datetime.utcnow)
    ts_submitted = Column(DateTime, nullable=True)
    ts_accepted = Column(DateTime, nullable=True)
    ts_terminal = Column(DateTime, nullable=True)

    tags = Column(JSON, default=list)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        Index(
            "ix_domain_orders_active_account",
            "account_id",
            "status",
        ),
    )


class ExecutionReportRow(Base):
    """Venue-stamped execution event.

    Keyed by ``(venue, venue_execution_id)`` -- the natural key the
    venue mints. Phase 3 reconciliation reads this table to build a
    deterministic state map that closes the WS-vs-REST race the
    Nautilus-trader issues #4012 / #3176 documented.
    """

    __tablename__ = "execution_reports"
    id = Column(String(36), primary_key=True, default=_uuid)
    venue = Column(String(32), nullable=False, index=True)
    venue_execution_id = Column(String(120), nullable=False)
    venue_order_id = Column(String(120), nullable=True, index=True)
    account_id = Column(String(64), nullable=True, index=True)

    client_order_id = Column(String(64), nullable=True, index=True)
    domain_order_id = Column(
        String(36),
        ForeignKey("domain_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    trade_id = Column(String(64), nullable=True)
    position_id = Column(String(64), nullable=True)

    report_kind = Column(String(24), nullable=False, index=True)
    # accepted | rejected | denied | submitted | triggered | filled |
    # partially_filled | canceled | expired | updated | pending_cancel |
    # pending_update | modify_rejected | emulated | released
    order_status = Column(String(24), nullable=True)
    order_side = Column(String(8), nullable=True)
    last_quantity = Column(Float, nullable=True)
    last_price = Column(Float, nullable=True)
    cumulative_quantity = Column(Float, nullable=True)
    average_fill_price = Column(Float, nullable=True)
    commission = Column(Float, nullable=True)
    commission_currency = Column(String(16), nullable=True)
    liquidity_side = Column(String(8), nullable=True)
    reason = Column(Text, nullable=True)

    ts_event = Column(DateTime, nullable=False, index=True)
    ts_received = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    seq_no = Column(Integer, nullable=True)

    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    meta = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "venue",
            "venue_execution_id",
            name="uq_execution_reports_venue_natural_key",
        ),
        Index(
            "ix_execution_reports_account_kind",
            "account_id",
            "report_kind",
        ),
    )


__all__ = [
    "DomainOrderRow",
    "ExecutionReportRow",
    "OrderListRow",
]
