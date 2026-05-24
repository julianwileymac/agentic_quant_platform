"""Market-data message types.

All are :class:`msgspec.Struct(gc=False, frozen=True)` for maximum
decode + dispatch throughput. The kernel's :class:`MessageBus` carries
these directly without an intermediate dict/dataclass copy.

The timestamp triple ``(exchange_ts_ns, ingress_ts_ns, processed_ts_ns)``
is mandatory on every event because backtest determinism (blueprint
§A.4) and microsecond latency budgeting (blueprint §J.3) both require
the kernel to know what time it is at every hop.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

import msgspec


class _MarketBase(msgspec.Struct, gc=False, frozen=True):
    """Common fields on every market event."""

    venue: str
    symbol: str
    exchange_ts_ns: int
    ingress_ts_ns: int
    processed_ts_ns: int = 0


class Tick(_MarketBase, gc=False, frozen=True):
    """Trade tick — a print on the public tape.

    ``side`` is the aggressor side; ``B`` = buyer-initiated,
    ``S`` = seller-initiated, ``U`` = unknown (e.g. opening auction).
    """

    price: Decimal
    size: Decimal
    side: Literal["B", "S", "U"] = "U"
    trade_id: str = ""


class Quote(_MarketBase, gc=False, frozen=True):
    """Top-of-book quote (BBO).

    For full depth use :class:`BookSnapshot`.
    """

    bid_px: Decimal
    bid_sz: Decimal
    ask_px: Decimal
    ask_sz: Decimal


class Bar(_MarketBase, gc=False, frozen=True):
    """Aggregated OHLCV bar.

    ``interval`` follows the ISO-8601 duration syntax (e.g. ``PT1M``,
    ``PT1H``, ``P1D``) or AQP's preset aliases (``1m``, ``5m``, ``1h``,
    ``1d``).
    """

    interval: str
    o: Decimal
    h: Decimal
    l: Decimal
    c: Decimal
    v: Decimal
    ts_open_ns: int = 0
    ts_close_ns: int = 0


class Trade(_MarketBase, gc=False, frozen=True):
    """Private trade — fills the bot's own orders generated.

    Distinct from :class:`Tick` (public tape). The strategy normally
    receives ``Fill`` from the execution layer; ``Trade`` is for venues
    that emit a separate stream of own-trade messages.
    """

    price: Decimal
    size: Decimal
    side: Literal["buy", "sell"]
    order_id: str
    trade_id: str = ""
    fee: Decimal = Decimal("0")
    fee_currency: str = ""


class BookLevel(msgspec.Struct, gc=False, frozen=True):
    """One level of an order book snapshot."""

    price: Decimal
    size: Decimal
    order_count: int = 0


class BookSnapshot(_MarketBase, gc=False, frozen=True):
    """Full depth-of-book snapshot.

    Adapters typically emit either deltas (use :class:`BookDelta` in a
    future iteration) or full snapshots at a throttled rate; the
    strategy can subscribe to whichever it can keep up with.
    """

    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    sequence_number: int = 0


# Union type for the kernel's bus dispatch.
MarketEvent = Tick | Quote | Bar | Trade | BookSnapshot


__all__ = [
    "Bar",
    "BookLevel",
    "BookSnapshot",
    "MarketEvent",
    "Quote",
    "Tick",
    "Trade",
]
