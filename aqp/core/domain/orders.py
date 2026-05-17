"""Rich order hierarchy + order-event family.

Expands the legacy flat :class:`aqp.core.types.OrderData` into a
nautilus-style polymorphic tree. Every order kind is a subclass of
:class:`DomainOrder` and adds the fields it needs (stop/limit/trigger/trail);
the event family (:class:`OrderAccepted`, :class:`OrderFilled`,
:class:`OrderCanceled`, :class:`OrderRejected`, :class:`OrderExpired`,
:class:`OrderTriggered`, :class:`OrderUpdated`, :class:`OrderPendingCancel`,
:class:`OrderPendingUpdate`, :class:`OrderModifyRejected`,
:class:`OrderEmulated`, :class:`OrderReleased`, :class:`OrderDenied`) records
every state transition so the ledger can reconstruct the full lifecycle.

The legacy ``OrderRequest``/``OrderData``/``OrderEvent``/``OrderTicket``
shapes are preserved in :mod:`aqp.core.types`; they delegate into this
module via a compatibility shim.

Phase 2 (migration 0041) makes this module the canonical wire shape:

* ``outside_rth`` -- allow execution outside regular trading hours
  (extended_hours on Alpaca, outsideRth on IBKR, ext_hours on Tradier)
* ``close_position`` -- auto-close the existing position (Binance-style);
  mutually exclusive with ``reduce_only``, enforced at submit time
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from aqp.core.domain.enums import (
    ContingencyType,
    LiquiditySide,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    TrailingOffsetType,
    TriggerType,
)
from aqp.core.domain.identifiers import (
    AccountId,
    ClientOrderId,
    ExecAlgorithmId,
    InstrumentId,
    OrderListId,
    PositionId,
    StrategyId,
    TraderId,
    TradeId,
    VenueOrderId,
)
from aqp.core.domain.money import Currency, Money


# ---------------------------------------------------------------------------
# Order base
# ---------------------------------------------------------------------------


@dataclass
class DomainOrder:
    """Base class for every concrete order shape.

    Named ``DomainOrder`` so it can coexist with the legacy ``OrderData`` in
    :mod:`aqp.core.types` during the migration window.
    """

    client_order_id: ClientOrderId
    instrument_id: InstrumentId
    order_side: OrderSide
    quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce = TimeInForce.DAY
    status: OrderStatus = OrderStatus.INITIALIZED

    venue_order_id: VenueOrderId | None = None
    account_id: AccountId | None = None
    trader_id: TraderId | None = None
    strategy_id: StrategyId | None = None
    position_id: PositionId | None = None
    exec_algorithm_id: ExecAlgorithmId | None = None
    order_list_id: OrderListId | None = None

    reduce_only: bool = False
    post_only: bool = False
    # Phase 2 (migration 0041): allow execution outside regular trading hours.
    outside_rth: bool = False
    # Phase 2 (migration 0041): auto-close the existing position. Mutually
    # exclusive with reduce_only when neither is True (default). When both are
    # True the validator at submit time rejects the order.
    close_position: bool = False

    good_till_date: datetime | None = None
    ts_init: datetime = field(default_factory=datetime.utcnow)
    ts_last: datetime = field(default_factory=datetime.utcnow)

    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal = Decimal("0")
    commissions: list[Money] = field(default_factory=list)

    linked_order_ids: list[ClientOrderId] = field(default_factory=list)
    contingency_type: ContingencyType = ContingencyType.NONE
    parent_order_id: ClientOrderId | None = None

    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in {
            OrderStatus.INITIALIZED,
            OrderStatus.SUBMITTING,
            OrderStatus.ACCEPTED,
            OrderStatus.PENDING_UPDATE,
            OrderStatus.PENDING_CANCEL,
            OrderStatus.EMULATED,
            OrderStatus.RELEASED,
            OrderStatus.TRIGGERED,
            OrderStatus.PARTIALLY_FILLED,
        }

    @property
    def is_terminal(self) -> bool:
        """Phase 2: order has reached a terminal state (no further transitions)."""
        return self.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
            OrderStatus.REJECTED,
            OrderStatus.DENIED,
        }

    @property
    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.filled_quantity

    def validate_flags(self) -> list[str]:
        """Phase 2: validate mutually-exclusive flag combinations.

        Returns a list of human-readable violations; empty list means
        the order is well-formed. Brokers + the contingency manager
        invoke this at submit time and reject the order on any
        violation.
        """
        violations: list[str] = []
        if self.reduce_only and self.close_position:
            violations.append(
                "reduce_only and close_position are mutually exclusive"
            )
        if self.post_only and self.order_type == OrderType.MARKET:
            violations.append("post_only requires a non-market order_type")
        if (
            self.time_in_force == TimeInForce.GTD
            and self.good_till_date is None
        ):
            violations.append("time_in_force=GTD requires good_till_date")
        if self.quantity <= 0 and not self.close_position:
            violations.append("quantity must be > 0 unless close_position=True")
        return violations


@dataclass
class MarketOrder(DomainOrder):
    order_type: OrderType = OrderType.MARKET


@dataclass
class LimitOrder(DomainOrder):
    order_type: OrderType = OrderType.LIMIT
    price: Decimal = Decimal("0")
    display_quantity: Decimal | None = None


@dataclass
class StopMarketOrder(DomainOrder):
    order_type: OrderType = OrderType.STOP_MARKET
    trigger_price: Decimal = Decimal("0")
    trigger_type: TriggerType = TriggerType.DEFAULT


@dataclass
class StopLimitOrder(DomainOrder):
    order_type: OrderType = OrderType.STOP_LIMIT
    trigger_price: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    trigger_type: TriggerType = TriggerType.DEFAULT
    display_quantity: Decimal | None = None


@dataclass
class MarketIfTouchedOrder(DomainOrder):
    order_type: OrderType = OrderType.MARKET_IF_TOUCHED
    trigger_price: Decimal = Decimal("0")
    trigger_type: TriggerType = TriggerType.DEFAULT


@dataclass
class LimitIfTouchedOrder(DomainOrder):
    order_type: OrderType = OrderType.LIMIT_IF_TOUCHED
    trigger_price: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    trigger_type: TriggerType = TriggerType.DEFAULT


@dataclass
class MarketToLimitOrder(DomainOrder):
    order_type: OrderType = OrderType.MARKET_TO_LIMIT
    price: Decimal | None = None


@dataclass
class TrailingStopMarketOrder(DomainOrder):
    order_type: OrderType = OrderType.TRAILING_STOP_MARKET
    trigger_price: Decimal | None = None
    trailing_offset: Decimal = Decimal("0")
    trailing_offset_type: TrailingOffsetType = TrailingOffsetType.PRICE
    trigger_type: TriggerType = TriggerType.DEFAULT


@dataclass
class TrailingStopLimitOrder(DomainOrder):
    order_type: OrderType = OrderType.TRAILING_STOP_LIMIT
    trigger_price: Decimal | None = None
    price: Decimal = Decimal("0")
    limit_offset: Decimal = Decimal("0")
    trailing_offset: Decimal = Decimal("0")
    trailing_offset_type: TrailingOffsetType = TrailingOffsetType.PRICE
    trigger_type: TriggerType = TriggerType.DEFAULT


# ---------------------------------------------------------------------------
# OrderList — a contingent group of orders
# ---------------------------------------------------------------------------


@dataclass
class OrderList:
    """Contingent order grouping (OCO / OUO / OTO)."""

    order_list_id: OrderListId
    orders: list[DomainOrder]
    contingency_type: ContingencyType = ContingencyType.OCO
    strategy_id: StrategyId | None = None
    parent_order_id: ClientOrderId | None = None
    # OTO only: the order whose fill triggers the others.
    ts_init: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        # Stamp the contingency type + order_list_id on every constituent
        # so any caller iterating the list can see the linkage without
        # having to also pass the parent.
        for order in self.orders:
            order.order_list_id = self.order_list_id
            order.contingency_type = self.contingency_type
            if self.parent_order_id is not None:
                order.parent_order_id = self.parent_order_id
            # Cross-link every order to its peers so OCO cancel cascades
            # work even on a single-order lookup.
            peer_ids = [
                o.client_order_id for o in self.orders if o is not order
            ]
            order.linked_order_ids = peer_ids

    def validate(self) -> list[str]:
        """Validate the list shape + each constituent.

        OCO requires >= 2 orders. OTO requires a parent_order_id matching
        one of the constituents. OUO requires exactly 2 orders.
        """
        violations: list[str] = []
        if not self.orders:
            violations.append("order list cannot be empty")
            return violations
        if self.contingency_type == ContingencyType.OCO and len(self.orders) < 2:
            violations.append("OCO requires at least 2 orders")
        if self.contingency_type == ContingencyType.OUO and len(self.orders) != 2:
            violations.append("OUO requires exactly 2 orders")
        if self.contingency_type == ContingencyType.OTO:
            if self.parent_order_id is None:
                violations.append("OTO requires parent_order_id")
            else:
                ids = {o.client_order_id for o in self.orders}
                if self.parent_order_id not in ids:
                    violations.append("OTO parent_order_id not in orders")
        for order in self.orders:
            violations.extend(
                f"[{order.client_order_id}] {v}" for v in order.validate_flags()
            )
        return violations


# ---------------------------------------------------------------------------
# Order events
# ---------------------------------------------------------------------------


@dataclass
class _OrderEventBase:
    """Shared fields on every order event."""

    client_order_id: ClientOrderId
    instrument_id: InstrumentId
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None
    event_id: str | None = None
    account_id: AccountId | None = None
    trader_id: TraderId | None = None
    strategy_id: StrategyId | None = None
    venue_order_id: VenueOrderId | None = None
    reason: str | None = None


@dataclass
class OrderInitialized(_OrderEventBase):
    order_type: OrderType = OrderType.MARKET
    order_side: OrderSide = OrderSide.BUY
    quantity: Decimal = Decimal("0")
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY


@dataclass
class OrderSubmitted(_OrderEventBase):
    pass


@dataclass
class OrderAccepted(_OrderEventBase):
    pass


@dataclass
class OrderRejected(_OrderEventBase):
    pass


@dataclass
class OrderDenied(_OrderEventBase):
    pass


@dataclass
class OrderEmulated(_OrderEventBase):
    pass


@dataclass
class OrderReleased(_OrderEventBase):
    released_price: Decimal | None = None


@dataclass
class OrderTriggered(_OrderEventBase):
    pass


@dataclass
class OrderPendingUpdate(_OrderEventBase):
    pass


@dataclass
class OrderPendingCancel(_OrderEventBase):
    pass


@dataclass
class OrderUpdated(_OrderEventBase):
    quantity: Decimal | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None


@dataclass
class OrderModifyRejected(_OrderEventBase):
    pass


@dataclass
class OrderCanceled(_OrderEventBase):
    pass


@dataclass
class OrderExpired(_OrderEventBase):
    pass


@dataclass
class OrderFilled(_OrderEventBase):
    trade_id: TradeId | None = None
    position_id: PositionId | None = None
    order_side: OrderSide = OrderSide.BUY
    last_quantity: Decimal = Decimal("0")
    last_price: Decimal = Decimal("0")
    currency: Currency | None = None
    commission: Money | None = None
    liquidity_side: LiquiditySide = LiquiditySide.NONE
