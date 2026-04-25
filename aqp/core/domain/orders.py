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
    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.filled_quantity


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
    ts_init: datetime = field(default_factory=datetime.utcnow)


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
