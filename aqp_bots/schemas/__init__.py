"""Hot-path message schemas for the QuantBot Platform.

These are :class:`msgspec.Struct` types optimized for the kernel runtime's
sub-millisecond decode + dispatch path. Per the official msgspec
benchmarks (jcristharif.com/msgspec/benchmarks.html), msgspec is ~12x
faster than Pydantic v2 for JSON decode + validation; we exploit that
gap on the wire-decode hot path while keeping :class:`pydantic.BaseModel`
for specs / manifests / CRDs (richer validator errors at the API boundary).

Rule of thumb:

- Pydantic for things humans author: ``BotSpec``, CRDs, REST request bodies.
- msgspec for things adapters emit at line rate: ``Tick``, ``Quote``, ``Bar``,
  ``NewOrder``, ``OrderAck``, ``Fill``, ``Reject``, ``Position``.

Every hot-path schema carries the (``exchange_ts_ns``, ``ingress_ts_ns``,
``processed_ts_ns``) timestamp triple so backtest sim and live trading
share the same clock contract (see blueprint §A.4 — research-to-live
parity).

All money fields use :class:`decimal.Decimal`. Floats are forbidden in
price/quantity carriers; NautilusTrader uses 128-bit fixed-point for the
hot path and we choose ``Decimal`` for portability with the option to
drop into Rust ``rust_decimal`` via PyO3 for extreme HFT bots.
"""
from __future__ import annotations

from aqp_bots.schemas.market import (
    Bar,
    BookSnapshot,
    MarketEvent,
    Quote,
    Tick,
    Trade,
)
from aqp_bots.schemas.trading import (
    Fill,
    NewOrder,
    OrderAck,
    OrderMod,
    OrderRef,
    OrderStatus,
    Position,
    ReconcileSnapshot,
    Reject,
    Side,
    TimeInForce,
)

__all__ = [
    "Bar",
    "BookSnapshot",
    "Fill",
    "MarketEvent",
    "NewOrder",
    "OrderAck",
    "OrderMod",
    "OrderRef",
    "OrderStatus",
    "Position",
    "Quote",
    "ReconcileSnapshot",
    "Reject",
    "Side",
    "Tick",
    "TimeInForce",
    "Trade",
]
