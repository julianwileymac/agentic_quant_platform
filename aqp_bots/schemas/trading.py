"""Trading message types — orders, acks, fills, rejects, positions.

All hot-path types are :class:`msgspec.Struct(gc=False, frozen=True)`.
The order lifecycle FSM (:mod:`aqp_bots.execution.lifecycle`) consumes
and emits these directly without a Pydantic round-trip.

Every type carries the canonical timestamp triple
(``exchange_ts_ns``, ``ingress_ts_ns``, ``processed_ts_ns``); the kernel
populates the ``processed_ts_ns`` field on dispatch so latency budgets
can be computed end-to-end.
"""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

import msgspec


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(StrEnum):
    GTC = "gtc"  # good 'til cancelled
    IOC = "ioc"  # immediate or cancel
    FOK = "fok"  # fill or kill
    DAY = "day"  # good for the trading day
    POST_ONLY = "post_only"  # maker-only


class OrderStatus(StrEnum):
    """Order lifecycle FSM states.

    Mirrors the blueprint §G.1 FSM:
    ``CREATED -> VALIDATED -> ROUTED -> ACKNOWLEDGED ->
    PARTIALLY_FILLED -> FILLED``
    plus the ``CANCEL_PENDING -> CANCELLED`` branch and
    terminal ``REJECTED`` / ``EXPIRED`` / ``DISPUTED`` states.
    """

    CREATED = "created"
    VALIDATED = "validated"
    ROUTED = "routed"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    DISPUTED = "disputed"


class OrderRef(msgspec.Struct, gc=False, frozen=True):
    """Stable cross-system identifier for an order.

    ``client_order_id`` is generated locally (UUIDv7 — time-ordered),
    ``venue_order_id`` is assigned by the venue on ack. The pair is
    the canonical key for idempotency (:mod:`aqp_bots.execution.idempotency`).
    """

    client_order_id: str
    venue_order_id: str = ""
    venue: str = ""
    symbol: str = ""


class NewOrder(msgspec.Struct, gc=False, frozen=True):
    """New-order request emitted by the strategy / execution algo.

    Created with :func:`aqp_bots.core.ids.new_client_order_id` — that
    helper returns a UUIDv7 + content hash for the dedup LRU.
    """

    venue: str
    symbol: str
    side: Side
    quantity: Decimal
    order_type: Literal["market", "limit", "stop", "stop_limit"]
    time_in_force: TimeInForce = TimeInForce.GTC
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    client_order_id: str = ""
    parent_order_id: str = ""  # set by execution algos (TWAP child orders)
    iceberg_qty: Decimal | None = None
    post_only: bool = False
    reduce_only: bool = False
    strategy_id: str = ""
    bot_id: str = ""
    correlation_id: str = ""
    exchange_ts_ns: int = 0
    ingress_ts_ns: int = 0
    processed_ts_ns: int = 0


class OrderMod(msgspec.Struct, gc=False, frozen=True):
    """Order modification (amend) request."""

    ref: OrderRef
    new_quantity: Decimal | None = None
    new_limit_price: Decimal | None = None
    new_stop_price: Decimal | None = None
    exchange_ts_ns: int = 0
    ingress_ts_ns: int = 0
    processed_ts_ns: int = 0


class OrderAck(msgspec.Struct, gc=False, frozen=True):
    """Venue acknowledgement of a new / amend / cancel.

    Emitted by an :class:`ExecutionAdapter` after the venue accepts the
    request and assigns a ``venue_order_id``. The kernel resolves the
    matching ``asyncio.Future`` in
    :class:`aqp_bots.core.futures.OrderFutureRegistry`.
    """

    ref: OrderRef
    status: OrderStatus
    accepted_quantity: Decimal = Decimal("0")
    venue_ts_ns: int = 0
    exchange_ts_ns: int = 0
    ingress_ts_ns: int = 0
    processed_ts_ns: int = 0


class Fill(msgspec.Struct, gc=False, frozen=True):
    """One partial or final fill on an order.

    Dedup key per blueprint §G.6 is the tuple ``(trade_date, exec_id,
    symbol, side, exec_type)`` — adapters MUST populate :attr:`exec_id`
    so the OMS can deduplicate venue replays without losing real
    duplicate prints from the same venue.
    """

    ref: OrderRef
    fill_qty: Decimal
    fill_price: Decimal
    side: Side
    cumulative_qty: Decimal
    leaves_qty: Decimal
    exec_id: str  # mandatory for dedup
    trade_date: str = ""  # YYYY-MM-DD in venue TZ
    exec_type: str = "trade"  # FIX 150 mapping (F=trade, etc.)
    fee: Decimal = Decimal("0")
    fee_currency: str = ""
    liquidity: Literal["maker", "taker", "unknown"] = "unknown"
    venue_ts_ns: int = 0
    exchange_ts_ns: int = 0
    ingress_ts_ns: int = 0
    processed_ts_ns: int = 0


class Reject(msgspec.Struct, gc=False, frozen=True):
    """Venue rejection of a new / amend / cancel."""

    ref: OrderRef
    reason_code: str
    reason_text: str = ""
    exchange_ts_ns: int = 0
    ingress_ts_ns: int = 0
    processed_ts_ns: int = 0


class Position(msgspec.Struct, gc=False, frozen=True):
    """Position snapshot for one ``(venue, symbol)`` pair.

    Net long / short representation: ``qty > 0`` = long, ``qty < 0`` =
    short, ``qty == 0`` = flat. ``avg_price`` is the volume-weighted
    average entry price across the open position.
    """

    venue: str
    symbol: str
    qty: Decimal
    avg_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    last_update_ns: int = 0


class ReconcileSnapshot(msgspec.Struct, gc=False, frozen=True):
    """Bulk venue-state snapshot emitted by ``reconcile()``.

    Returned by :meth:`ExecutionAdapter.reconcile` on (re)connect; the
    OMS diffs this against its in-memory ledger and emits
    ``DISPUTED`` events for mismatches per blueprint §G.5.
    """

    venue: str
    open_orders: tuple[OrderRef, ...]
    positions: tuple[Position, ...]
    snapshot_ts_ns: int


__all__ = [
    "Fill",
    "NewOrder",
    "OrderAck",
    "OrderMod",
    "OrderRef",
    "OrderStatus",
    "Position",
    "ReconcileSnapshot",
    "Reject",
    "Side",
    "TimeInForce",
]
