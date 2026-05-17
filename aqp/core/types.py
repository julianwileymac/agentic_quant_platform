"""LEGACY compatibility shim over :mod:`aqp.core.domain`.

This module is the historical home of AQP's core value objects. As of the
Phase 1-5 finalization, every type that has a richer equivalent in
:mod:`aqp.core.domain` is now a **deprecated shim** -- the public API is
preserved for backward compatibility, but the canonical state and
behaviour live in the domain module.

New code MUST prefer the domain types. The shim layer is kept only to
support the ~140 existing importers across the codebase during the
migration window.

Migration map
-------------
============================ =============================================
Legacy (this module)         Canonical (domain)
============================ =============================================
:class:`Symbol`              :class:`aqp.core.domain.identifiers.InstrumentId`
:class:`Exchange`            :class:`aqp.core.domain.identifiers.Venue`
:class:`AssetClass`          :class:`aqp.core.domain.enums.AssetClass` (richer)
:class:`SecurityType`        :class:`aqp.core.domain.enums.InstrumentClass`
:class:`OrderType`           :class:`aqp.core.domain.enums.OrderType` (superset)
:class:`OrderSide`           :class:`aqp.core.domain.enums.OrderSide` (superset)
:class:`OrderStatus`         :class:`aqp.core.domain.enums.OrderStatus` (superset)
:class:`OrderRequest`        :class:`aqp.core.domain.orders.DomainOrder`
:class:`OrderData`           :class:`aqp.core.domain.orders.DomainOrder` (view)
:class:`AccountData`         :class:`aqp.persistence.models_accounts.AccountRow` + balances
:class:`PositionData`        :class:`aqp.persistence.models_accounts.AccountPositionRow`
:class:`TradeData`           :class:`aqp.trading.execution.ExecutionReport`
============================ =============================================

Domain bridges
--------------
Every legacy class that has a domain equivalent now exposes a bridge
method so callers can incrementally migrate without rewriting their
imports:

* :meth:`Symbol.to_instrument_id` / :meth:`Symbol.from_instrument_id`
* :meth:`OrderRequest.to_domain_order` (Phase 2 adapter)
* :meth:`OrderData.to_domain_order` /
  :meth:`OrderData.from_domain_order`
* :meth:`TradeData.from_execution_report`
* :meth:`PositionData.from_account_position_row`
* :meth:`AccountData.from_account_row`

Domain re-exports
-----------------
The recommended migration is to swap ``from aqp.core.types import X`` for
``from aqp.core.domain import X``. For files that can't do the import
swap immediately, every Phase 1-5 domain class is also re-exported here:

.. code-block:: python

    # Both of these now work, but the second is the recommended path
    from aqp.core.types import DomainOrder, InstrumentId, RiskMeasure
    from aqp.core.domain import DomainOrder, InstrumentId, RiskMeasure

Types with no domain replacement
--------------------------------
These remain authoritative in this module (the domain layer has nothing
equivalent and probably never will):

* :class:`BarData`, :class:`TradeBar`, :class:`QuoteBar`, :class:`TickData`,
  :class:`Tick` -- market-data records (the domain layer is about
  identity + orders + accounts, not the data plane)
* :class:`Interval`, :class:`Resolution`, :class:`TickType`,
  :class:`DataNormalizationMode`, :class:`SubscriptionDataConfig` --
  data-plane routing keys
* :class:`Signal`, :class:`PortfolioTarget` -- alpha / portfolio
  framework value objects
* :class:`Event`, :class:`MarketEvent`, :class:`SignalEvent`,
  :class:`OrderEvent_Msg`, :class:`FillEvent_Msg`, :class:`EventType` --
  backtest event loop
* :class:`OrderEvent`, :class:`OrderTicket` -- legacy framework
  patterns kept for the existing :class:`PaperTradingSession`
* :class:`Cash`, :class:`CashBook` -- multi-currency accounting helpers
* :class:`SecurityHolding` -- legacy Lean-style position record
* :class:`Direction` -- LONG/SHORT/NET (overlaps with
  ``PositionSide`` but values differ)
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aqp.core.domain.orders import DomainOrder as _DomainOrder
    from aqp.core.domain.identifiers import InstrumentId as _InstrumentId


# ---------------------------------------------------------------------------
# Enumerations (legacy)
# ---------------------------------------------------------------------------
# Every enum below has a richer equivalent under aqp.core.domain.enums.
# The legacy enums are kept verbatim because (a) the legacy values are
# persisted in existing DB columns + YAML files (renaming would force a
# data migration), and (b) the domain enums use slightly different naming
# conventions (CANCELLED -> CANCELED, PARTIAL -> PARTIALLY_FILLED, etc.).
#
# Callers needing the richer vocabulary import directly from
# aqp.core.domain.enums.
# ---------------------------------------------------------------------------


class Exchange(StrEnum):
    """Legacy execution venue enum.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.identifiers.Venue` for new code. The
       domain :class:`Venue` is a string-valued ID rather than an enum,
       so it accepts any venue code without requiring an entry here.
    """

    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    ARCA = "ARCA"
    BATS = "BATS"
    CBOE = "CBOE"
    CME = "CME"
    LSE = "LSE"
    LOCAL = "LOCAL"
    BINANCE = "BINANCE"
    COINBASE = "COINBASE"
    SIM = "SIM"


class AssetClass(StrEnum):
    """Legacy asset-class enum.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.enums.AssetClass` for new code -- it
       carries the additional ``RATES``, ``CREDIT``, ``ALTERNATIVE``,
       ``EVENT``, ``MIXED``, and ``CASH`` families.
    """

    EQUITY = "equity"
    CRYPTO = "crypto"
    FX = "fx"
    FUTURE = "future"
    OPTION = "option"
    INDEX = "index"
    COMMODITY = "commodity"
    BOND = "bond"
    BASE = "base"


class SecurityType(StrEnum):
    """Lean-style security type (legacy).

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.enums.InstrumentClass` -- it covers
       SPOT/FUTURE/FORWARD/OPTION/SWAP/CFD/ETF/INDEX/BOND/PERPETUAL plus
       the Phase 1 additions (REIT/MUTUAL_FUND/OTC_DERIVATIVE/ADR/GDR).
    """

    BASE = "base"
    EQUITY = "equity"
    OPTION = "option"
    FUTURE = "future"
    FUTURE_OPTION = "future_option"
    FOREX = "forex"
    CFD = "cfd"
    CRYPTO = "crypto"
    CRYPTO_FUTURE = "crypto_future"
    INDEX = "index"
    INDEX_OPTION = "index_option"
    COMMODITY = "commodity"


class Direction(StrEnum):
    """Legacy position-direction enum.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.enums.PositionSide` -- it has
       ``LONG``/``SHORT``/``FLAT`` and matches the Phase 3 ``position_side``
       column on :class:`AccountPositionRow`.
    """

    LONG = "long"
    SHORT = "short"
    NET = "net"


class OrderType(StrEnum):
    """Legacy order-type enum.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.enums.OrderType` -- the domain enum
       adds STOP_MARKET / MARKET_IF_TOUCHED / LIMIT_IF_TOUCHED /
       MARKET_TO_LIMIT / TRAILING_STOP_MARKET / TRAILING_STOP_LIMIT /
       FOK / FAK / RFQ that the Phase 2 unification needs.
    """

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    MARKET_ON_OPEN = "market_on_open"
    MARKET_ON_CLOSE = "market_on_close"
    TRAILING_STOP = "trailing_stop"


class OrderSide(StrEnum):
    """Legacy order-side enum.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.enums.OrderSide` (adds ``NONE``).
    """

    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    """Legacy order-status enum.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.enums.OrderStatus` -- the domain enum
       has the richer state machine (INITIALIZED / SUBMITTING / ACCEPTED /
       PENDING_UPDATE / PENDING_CANCEL / EMULATED / RELEASED / TRIGGERED /
       PARTIALLY_FILLED / FILLED / CANCELED / EXPIRED / REJECTED / DENIED).
       Legacy ``CANCELLED`` (two L's) maps to domain ``CANCELED`` (one L).
    """

    SUBMITTING = "submitting"
    NEW = "new"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


ACTIVE_STATUSES = {OrderStatus.SUBMITTING, OrderStatus.NEW, OrderStatus.PARTIAL}


class Interval(StrEnum):
    """Short-code bar cadence (vnpy style). ``Resolution`` is the Lean-style enum.

    Kept as the canonical interval enum -- the domain layer is about
    identity / orders / accounts, not the data plane.
    """

    TICK = "tick"
    SECOND = "1s"
    FIVE_SECOND = "5s"
    TEN_SECOND = "10s"
    MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"


class Resolution(StrEnum):
    """Lean-style data resolution enum with ``timedelta`` helpers.

    Kept as the canonical resolution enum -- no domain equivalent.
    """

    TICK = "tick"
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAILY = "daily"

    def to_timedelta(self) -> timedelta:
        return {
            Resolution.TICK: timedelta(0),
            Resolution.SECOND: timedelta(seconds=1),
            Resolution.MINUTE: timedelta(minutes=1),
            Resolution.HOUR: timedelta(hours=1),
            Resolution.DAILY: timedelta(days=1),
        }[self]

    def to_interval(self) -> Interval:
        return {
            Resolution.TICK: Interval.TICK,
            Resolution.SECOND: Interval.SECOND,
            Resolution.MINUTE: Interval.MINUTE,
            Resolution.HOUR: Interval.HOUR,
            Resolution.DAILY: Interval.DAY,
        }[self]

    @classmethod
    def from_interval(cls, interval: str | Interval) -> Resolution:
        raw = interval.value if isinstance(interval, Interval) else str(interval)
        mapping = {
            "tick": cls.TICK,
            "1s": cls.SECOND,
            "1m": cls.MINUTE,
            "5m": cls.MINUTE,
            "15m": cls.MINUTE,
            "1h": cls.HOUR,
            "1d": cls.DAILY,
            "1w": cls.DAILY,
        }
        return mapping.get(raw, cls.DAILY)


class TickType(StrEnum):
    """Lean ``TickType`` -- what a tick represents. No domain equivalent."""

    TRADE = "trade"
    QUOTE = "quote"
    OPEN_INTEREST = "open_interest"


class DataNormalizationMode(StrEnum):
    """How historical prices are adjusted for corporate actions. No domain equivalent."""

    RAW = "raw"
    ADJUSTED = "adjusted"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"


# ---------------------------------------------------------------------------
# Symbol -- legacy compat-facade over InstrumentId
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """Immutable composite identifier. Mirrors vnpy's ``vt_symbol`` pattern.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.identifiers.InstrumentId` -- the
       domain shape carries ``Symbol2`` + ``Venue`` value objects (each
       hashable and strictly-typed). :meth:`Symbol.to_instrument_id`
       bridges this legacy class to the domain shape; subsequent code
       paths should prefer the domain id.

    The legacy public surface (``ticker``, ``exchange``, ``vt_symbol``,
    ``parse``) is preserved so existing strategies + brokers keep
    importing :class:`Symbol`. New code should reach for
    :class:`InstrumentId` directly.
    """

    ticker: str
    exchange: Exchange = Exchange.NASDAQ
    asset_class: AssetClass = AssetClass.EQUITY
    security_type: SecurityType = SecurityType.EQUITY

    @property
    def vt_symbol(self) -> str:
        return f"{self.ticker}.{self.exchange.value}"

    def __str__(self) -> str:
        return self.vt_symbol

    @classmethod
    def parse(cls, vt: str) -> Symbol:
        """Parse a ``TICKER.VENUE`` vt_symbol string.

        Hard rule 1 (AGENTS.md): never split a vt_symbol on '.' by hand;
        always call :meth:`Symbol.parse`.
        """
        if "." not in vt:
            return cls(ticker=vt)
        ticker, exch = vt.rsplit(".", 1)
        try:
            exchange = Exchange(exch)
        except ValueError:
            exchange = Exchange.LOCAL
        return cls(ticker=ticker, exchange=exchange)

    def to_instrument_id(self) -> _InstrumentId:
        """Bridge to the canonical :class:`InstrumentId`.

        Lazy-imports the domain module so this helper doesn't add startup
        cost for callers that never reach for the richer type.
        """
        from aqp.core.domain.identifiers import InstrumentId, Symbol2, Venue

        return InstrumentId(
            symbol=Symbol2(self.ticker),
            venue=Venue(self.exchange.value),
        )

    @classmethod
    def from_instrument_id(cls, instrument_id: Any) -> Symbol:
        """Bridge from a domain :class:`InstrumentId` back to this legacy class."""
        ticker = (
            instrument_id.symbol.value
            if hasattr(instrument_id, "symbol")
            else str(instrument_id)
        )
        venue = (
            instrument_id.venue.value
            if hasattr(instrument_id, "venue")
            else "LOCAL"
        )
        try:
            exchange = Exchange(venue)
        except ValueError:
            exchange = Exchange.LOCAL
        return cls(ticker=ticker, exchange=exchange)


# ---------------------------------------------------------------------------
# Subscription routing (Lean ``SubscriptionDataConfig``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionDataConfig:
    """Data-plane routing key. No domain equivalent."""

    symbol: Symbol
    resolution: Resolution = Resolution.DAILY
    tick_type: TickType = TickType.TRADE
    fill_forward: bool = True
    extended_hours: bool = False
    normalization: DataNormalizationMode = DataNormalizationMode.ADJUSTED
    is_custom_data: bool = False
    is_internal_feed: bool = False

    @property
    def vt_symbol(self) -> str:
        return self.symbol.vt_symbol

    @property
    def increment(self) -> timedelta:
        return self.resolution.to_timedelta()


# ---------------------------------------------------------------------------
# Market data (bars, quote bars, ticks). No domain equivalents.
# ---------------------------------------------------------------------------


@dataclass
class BarData:
    """Trade OHLCV bar. Alias: ``TradeBar`` (Lean naming)."""

    symbol: Symbol
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: Interval = Interval.DAY
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def vt_symbol(self) -> str:
        return self.symbol.vt_symbol

    @property
    def value(self) -> float:
        """Lean parity -- ``BaseData.Value`` maps to the close price."""
        return self.close

    @property
    def period(self) -> timedelta:
        """Bar period inferred from ``interval``."""
        return Resolution.from_interval(self.interval).to_timedelta()


TradeBar = BarData


@dataclass
class QuoteBar:
    """Bid/ask OHLC bar (Lean ``QuoteBar``)."""

    symbol: Symbol
    timestamp: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    interval: Interval = Interval.MINUTE

    @property
    def vt_symbol(self) -> str:
        return self.symbol.vt_symbol

    @property
    def mid_close(self) -> float:
        return (self.bid_close + self.ask_close) / 2

    @property
    def mid_open(self) -> float:
        return (self.bid_open + self.ask_open) / 2

    @property
    def spread_close(self) -> float:
        return self.ask_close - self.bid_close


@dataclass
class TickData:
    """Point-in-time quote tick. Alias: ``Tick`` (Lean naming)."""

    symbol: Symbol
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    tick_type: TickType = TickType.QUOTE

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


Tick = TickData


# ---------------------------------------------------------------------------
# Orders, tickets, events -- legacy compat-shims over DomainOrder
# ---------------------------------------------------------------------------


@dataclass
class OrderRequest:
    """Legacy thin order intent dataclass.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.orders.DomainOrder` (or one of its
       subclasses: :class:`MarketOrder`, :class:`LimitOrder`,
       :class:`StopMarketOrder`, ...). The domain shape carries
       post_only / reduce_only / outside_rth / close_position /
       display_quantity / trigger_type / trailing_offset_type plus
       contingency-graph linkage -- the Phase 2 unification needs all
       of those.

    The :meth:`to_domain_order` bridge handles the conversion through
    :func:`aqp.trading.execution.legacy_adapter.domain_order_from_order_request`.
    """

    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    reference: str | None = None
    strategy_id: str | None = None
    time_in_force: str = "day"

    def create_order(self, order_id: str, gateway: str) -> OrderData:
        """Materialise the request into a legacy :class:`OrderData` row.

        Kept for back-compat with :class:`PaperTradingSession`. New code
        should use :meth:`to_domain_order` instead.
        """
        return OrderData(
            order_id=order_id,
            gateway=gateway,
            symbol=self.symbol,
            side=self.side,
            order_type=self.order_type,
            quantity=self.quantity,
            price=self.price,
            stop_price=self.stop_price,
            status=OrderStatus.SUBMITTING,
            reference=self.reference,
            strategy_id=self.strategy_id,
            created_at=datetime.utcnow(),
            time_in_force=self.time_in_force,
        )

    def to_domain_order(
        self,
        *,
        client_order_id: str | None = None,
        gateway: str | None = None,
        account: str | None = None,
    ) -> _DomainOrder:
        """Bridge this legacy request into a :class:`DomainOrder`.

        Delegates to the Phase 2
        :func:`aqp.trading.execution.legacy_adapter.domain_order_from_order_request`
        helper so legacy callers can produce a domain order with one method
        call.
        """
        from aqp.trading.execution.legacy_adapter import (
            domain_order_from_order_request,
        )

        return domain_order_from_order_request(
            self,
            client_order_id=client_order_id,
            gateway=gateway,
            account=account,
        )


@dataclass
class OrderData:
    """Legacy order-state row.

    .. deprecated:: 5.0
       Use :class:`aqp.core.domain.orders.DomainOrder` -- the domain shape
       carries the full state machine, contingency graph linkage, and
       the Phase 2 advanced-order flags.

    The :meth:`to_domain_order` bridge materialises a fresh
    :class:`DomainOrder` from this row; :meth:`from_domain_order`
    builds a legacy :class:`OrderData` view from an existing domain order
    (useful for keeping :class:`PaperTradingSession` happy while the
    underlying broker has already migrated).
    """

    order_id: str
    gateway: str
    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    quantity: float
    status: OrderStatus
    price: float | None = None
    stop_price: float | None = None
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    reference: str | None = None
    strategy_id: str | None = None
    time_in_force: str = "day"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def vt_order_id(self) -> str:
        return f"{self.gateway}.{self.order_id}"

    def to_domain_order(self) -> _DomainOrder:
        """Bridge this legacy row into a fresh :class:`DomainOrder`.

        Synthesises an :class:`OrderRequest` from the row + dispatches
        through the Phase 2 legacy adapter. Useful when a legacy
        :class:`OrderData` lives in a Redis cache and the caller needs
        domain-shape state to drive a contingency-manager decision.
        """
        request = OrderRequest(
            symbol=self.symbol,
            side=self.side,
            order_type=self.order_type,
            quantity=self.quantity,
            price=self.price,
            stop_price=self.stop_price,
            reference=self.reference,
            strategy_id=self.strategy_id,
            time_in_force=self.time_in_force,
        )
        return request.to_domain_order(
            client_order_id=self.order_id, gateway=self.gateway
        )

    @classmethod
    def from_domain_order(
        cls, order: _DomainOrder, *, gateway: str = "domain"
    ) -> OrderData:
        """Project a :class:`DomainOrder` back into legacy :class:`OrderData` shape.

        Mirror of :func:`aqp.trading.execution.legacy_adapter.order_data_from_domain_order`,
        re-exposed as a classmethod for convenience.
        """
        from aqp.trading.execution.legacy_adapter import (
            order_data_from_domain_order,
        )

        return order_data_from_domain_order(order, gateway=gateway)


@dataclass
class TradeData:
    """Legacy fill / trade record.

    .. deprecated:: 5.0
       Use :class:`aqp.trading.execution.ExecutionReport` -- the Phase 2
       audit DTO that's keyed on the venue-natural
       ``(venue, venue_execution_id)`` pair, eliminating the WS-vs-REST
       duplicate-event race documented in Nautilus #4012.
    """

    trade_id: str
    order_id: str
    symbol: Symbol
    side: OrderSide
    price: float
    quantity: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    commission: float = 0.0
    slippage: float = 0.0
    strategy_id: str | None = None

    @classmethod
    def from_execution_report(cls, report: Any) -> TradeData:
        """Bridge a Phase 2 :class:`ExecutionReport` into legacy shape."""
        sym = Symbol(
            ticker=str(report.vt_symbol or "").split(".", 1)[0]
            if getattr(report, "vt_symbol", None)
            else "UNKNOWN",
            exchange=_exchange_from_venue(getattr(report, "venue", "LOCAL")),
        )
        side = (
            OrderSide.BUY
            if str(getattr(report, "order_side", "buy")).lower() == "buy"
            else OrderSide.SELL
        )
        return cls(
            trade_id=str(getattr(report, "trade_id", "") or report.venue_execution_id),
            order_id=str(getattr(report, "client_order_id", "") or ""),
            symbol=sym,
            side=side,
            price=float(getattr(report, "last_price", 0.0) or 0.0),
            quantity=float(getattr(report, "last_quantity", 0.0) or 0.0),
            timestamp=getattr(report, "ts_event", datetime.utcnow()),
            commission=float(getattr(report, "commission", 0.0) or 0.0),
        )


@dataclass
class OrderEvent:
    """Order state-transition / fill message (Lean ``OrderEvent``).

    Legacy framework type kept for the existing :class:`PaperTradingSession`.
    New code should consume :class:`aqp.trading.execution.ExecutionReport`
    directly via the Phase 2 dispatcher.
    """

    order_id: str
    timestamp: datetime
    status: OrderStatus
    direction: OrderSide
    fill_price: float = 0.0
    fill_quantity: float = 0.0
    fee: float = 0.0
    message: str | None = None
    symbol: Symbol | None = None

    @property
    def is_fill(self) -> bool:
        return self.fill_quantity > 0 and self.status in {
            OrderStatus.PARTIAL,
            OrderStatus.FILLED,
        }


@dataclass
class OrderTicket:
    """Stable handle to a placed order + its event stream (Lean pattern).

    Legacy framework type. New code should keep a :class:`DomainOrder` and
    subscribe to :class:`ExecutionReport` events via the Phase 2 dispatcher
    rather than maintaining an in-memory ticket.
    """

    order: OrderData
    events: list[OrderEvent] = field(default_factory=list)

    @property
    def order_id(self) -> str:
        return self.order.order_id

    @property
    def status(self) -> OrderStatus:
        return self.order.status

    def is_active(self) -> bool:
        return self.order.is_active()

    def append_event(self, event: OrderEvent) -> None:
        """Record an ``OrderEvent`` and update ``order`` in-place."""
        self.events.append(event)
        self.order.status = event.status
        self.order.updated_at = event.timestamp
        if event.fill_quantity > 0:
            prev_qty = self.order.filled_quantity
            new_qty = prev_qty + event.fill_quantity
            prev_px = self.order.average_fill_price
            if new_qty > 0:
                self.order.average_fill_price = (
                    prev_px * prev_qty + event.fill_price * event.fill_quantity
                ) / new_qty
            self.order.filled_quantity = new_qty

    def last_event(self) -> OrderEvent | None:
        return self.events[-1] if self.events else None


# ---------------------------------------------------------------------------
# Positions, holdings, cash book
# ---------------------------------------------------------------------------


@dataclass
class PositionData:
    """Legacy position snapshot.

    .. deprecated:: 5.0
       Use :class:`aqp.persistence.models_accounts.AccountPositionRow` --
       the Phase 3 persistence row that supports the composite
       ``(account_pk, venue, vt_symbol, position_side)`` key for hedge-mode
       venues (closes Nautilus #4012).
    """

    symbol: Symbol
    direction: Direction
    quantity: float
    average_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @property
    def notional(self) -> float:
        return self.quantity * self.average_price

    @classmethod
    def from_account_position_row(cls, row: Any) -> PositionData:
        """Bridge a Phase 3 ``AccountPositionRow`` into legacy shape."""
        qty = float(row.quantity or 0.0)
        direction = Direction.LONG if qty >= 0 else Direction.SHORT
        sym = Symbol.parse(str(row.vt_symbol))
        return cls(
            symbol=sym,
            direction=direction,
            quantity=abs(qty),
            average_price=float(row.average_entry_price or 0.0),
            unrealized_pnl=float(row.unrealized_pnl or 0.0),
            realized_pnl=float(row.realized_pnl or 0.0),
        )


@dataclass
class SecurityHolding:
    """Extended Lean-style position record.

    Legacy framework type kept for the strategy code that already uses it.
    Phase 3+ code should read positions directly from
    :class:`AccountPositionRow` (no equivalent of the ``target``
    back-reference is needed once strategies use
    :class:`PortfolioTarget` separately).
    """

    symbol: Symbol
    direction: Direction
    quantity: float
    average_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    fees: float = 0.0
    last_trade_ts: datetime | None = None
    target: PortfolioTarget | None = None

    @property
    def notional(self) -> float:
        return self.quantity * self.average_price

    @property
    def absolute_quantity(self) -> float:
        return abs(self.quantity)

    @classmethod
    def from_position(cls, position: PositionData) -> SecurityHolding:
        return cls(
            symbol=position.symbol,
            direction=position.direction,
            quantity=position.quantity,
            average_price=position.average_price,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
        )


@dataclass
class Cash:
    """A balance in a single currency.

    Legacy multi-currency accounting helper. The Phase 3
    :class:`AccountBalanceRow` is the canonical persistence row for
    per-currency, per-balance-kind tracking; :class:`Cash` remains for
    the in-memory paper-session ledger.
    """

    currency: str = "USD"
    amount: float = 0.0
    conversion_rate: float = 1.0

    @property
    def value_in_account_currency(self) -> float:
        return self.amount * self.conversion_rate

    def deposit(self, amount: float) -> None:
        self.amount += amount

    def withdraw(self, amount: float) -> None:
        self.amount -= amount


class CashBook(dict):
    """Multi-currency balance book (Lean ``CashBook``).

    Legacy framework type kept for the in-memory paper-session ledger.
    Phase 3+ code reads balances from
    :class:`AccountBalanceRow` keyed by ``(currency, balance_kind)``.
    """

    def __init__(
        self, account_currency: str = "USD", initial: dict[str, Cash] | None = None
    ) -> None:
        super().__init__(initial or {})
        self.account_currency = account_currency
        self.setdefault(account_currency, Cash(currency=account_currency, amount=0.0))

    def ensure(self, currency: str) -> Cash:
        if currency not in self:
            self[currency] = Cash(currency=currency, amount=0.0)
        return self[currency]

    @property
    def total_value_in_account_currency(self) -> float:
        return sum(c.value_in_account_currency for c in self.values())


@dataclass
class AccountData:
    """Legacy in-memory account snapshot.

    .. deprecated:: 5.0
       Use :class:`aqp.persistence.models_accounts.AccountRow` plus
       :class:`AccountBalanceRow` -- the Phase 3 persistence rows that
       segregate CASH from MARGIN_INITIAL / MARGIN_MAINTENANCE /
       BUYING_POWER. The single-float ``cash`` here can't represent
       margin-account economics correctly.

    The :meth:`from_account_row` bridge builds a legacy
    :class:`AccountData` snapshot from the canonical persistence rows
    so existing consumers (PaperTradingSession, REST routes) keep
    working without changes.
    """

    account_id: str
    cash: float
    equity: float
    margin_used: float = 0.0
    currency: str = "USD"
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_account_row(
        cls,
        account_row: Any,
        balances: list[Any] | None = None,
    ) -> AccountData:
        """Build a legacy snapshot from the Phase 3 persistence rows.

        ``account_row`` is a :class:`AccountRow`; ``balances`` is a list
        of :class:`AccountBalanceRow`. The snapshot aggregates CASH +
        UNREALIZED_PNL into ``equity`` and ``MARGIN_INITIAL`` into
        ``margin_used`` so the legacy field names stay accurate even when
        the underlying data is far richer.
        """
        cash_total = 0.0
        margin_used = 0.0
        equity = 0.0
        currency = getattr(account_row, "base_currency", None) or "USD"
        for row in balances or ():
            row_currency = getattr(row, "currency", currency)
            amount = float(getattr(row, "amount", 0.0) or 0.0)
            kind = str(getattr(row, "balance_kind", "")).upper()
            if row_currency != currency:
                continue
            if kind == "CASH":
                cash_total += amount
                equity += amount
            elif kind in ("UNREALIZED_PNL", "REALIZED_PNL_DAY"):
                equity += amount
            elif kind == "MARGIN_INITIAL":
                margin_used += amount
        return cls(
            account_id=str(getattr(account_row, "account_id", "")),
            cash=cash_total,
            equity=equity,
            margin_used=margin_used,
            currency=currency,
            updated_at=getattr(account_row, "updated_at", datetime.utcnow()),
        )


# ---------------------------------------------------------------------------
# Framework value objects (no domain equivalents)
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    MARKET = "MARKET"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"


@dataclass
class Event:
    """Base event for the central engine queue."""

    timestamp: datetime
    type: EventType


@dataclass
class MarketEvent(Event):
    """Encapsulates a market data update (Bar or Tick)."""

    data: BarData | TickData | QuoteBar

    def __init__(self, data: BarData | TickData | QuoteBar):
        self.timestamp = data.timestamp if hasattr(data, "timestamp") else datetime.utcnow()
        self.type = EventType.MARKET
        self.data = data


@dataclass
class SignalEvent(Event):
    """Emitted by an Alpha model when it has an Insight."""

    signals: list[Signal]

    def __init__(self, signals: list[Signal], timestamp: datetime | None = None):
        self.timestamp = timestamp or (signals[0].timestamp if signals else datetime.utcnow())
        self.type = EventType.SIGNAL
        self.signals = signals


@dataclass
class OrderEvent_Msg(Event):  # noqa: N801 - back-compat name, can't rename
    """Emitted by the execution layer to request an order.

    ``order_id`` is populated by the broker after :meth:`IBrokerage.submit_order`
    and surfaces here so the event log carries enough state for
    :func:`aqp.backtest.replay.replay_event_log` to correlate downstream
    ``FillEvent_Msg`` rows back to their originating order.
    """

    request: OrderRequest
    order_id: str | None = None

    def __init__(
        self,
        request: OrderRequest,
        timestamp: datetime | None = None,
        order_id: str | None = None,
    ):
        self.timestamp = timestamp or datetime.utcnow()
        self.type = EventType.ORDER
        self.request = request
        self.order_id = order_id


@dataclass
class FillEvent_Msg(Event):  # noqa: N801 - back-compat name, can't rename
    """Emitted by the brokerage when a trade occurs."""

    trade: TradeData

    def __init__(self, trade: TradeData, timestamp: datetime | None = None):
        self.timestamp = timestamp or trade.timestamp
        self.type = EventType.FILL
        self.trade = trade


@dataclass
class Signal:
    """Alpha-level intent before portfolio construction (Lean ``Insight``)."""

    symbol: Symbol
    strength: float
    direction: Direction
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    horizon_days: int = 1
    source: str = "unknown"
    rationale: str | None = None


@dataclass
class PortfolioTarget:
    """Lean-style target weight emitted by the PortfolioConstructionModel."""

    symbol: Symbol
    target_weight: float
    rationale: str | None = None
    horizon_days: int = 1


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def money(value: float | Decimal) -> float:
    """Convenience rounder for accounting display (not for computation)."""
    return round(float(value), 4)


def iter_subscriptions(
    symbols: Iterable[Symbol],
    resolution: Resolution = Resolution.DAILY,
) -> Iterator[SubscriptionDataConfig]:
    """Produce a default ``SubscriptionDataConfig`` per symbol."""
    for s in symbols:
        yield SubscriptionDataConfig(symbol=s, resolution=resolution)


def _exchange_from_venue(venue: str) -> Exchange:
    """Best-effort map a venue string into the legacy :class:`Exchange` enum.

    Used by :meth:`TradeData.from_execution_report` to bridge the
    Phase 2 ``venue`` string back to the legacy enum. Unknown venues
    fall back to ``Exchange.LOCAL``.
    """
    if not venue:
        return Exchange.LOCAL
    try:
        return Exchange(venue.upper())
    except ValueError:
        return Exchange.LOCAL


# ---------------------------------------------------------------------------
# Domain re-exports
# ---------------------------------------------------------------------------
# Callers can import any Phase 1-5 domain type from this legacy module so
# the migration is a one-line `from aqp.core.types import DomainOrder`
# rather than a full import-line rewrite. The long-term recommendation is
# `from aqp.core.domain import ...` (or the specific submodule), but this
# bridge keeps the door open for incremental migration.
#
# Wrapped in a try/except because some bootstrap paths can import this
# module before domain submodules are loadable (early imports during
# Alembic env.py setup); the fallback assigns None so callers that do try
# to import a domain name get a clear AttributeError.
# ---------------------------------------------------------------------------

try:
    from aqp.core.domain.enums import (
        AccountType as DomainAccountType,
        AggressorSide,
        AssetClass as DomainAssetClass,
        BarAggregation,
        BookAction,
        BookType,
        ContingencyType,
        CorporateActionKind,
        FilingType,
        IndustryClassificationScheme,
        InstrumentClass,
        InstrumentCloseType,
        LiquiditySide,
        MarketStatus,
        Offset,
        OmsType,
        OptionKind,
        OptionStyle,
        OrderSide as DomainOrderSide,
        OrderStatus as DomainOrderStatus,
        OrderType as DomainOrderType,
        PayReceive,
        PositionSide,
        PriceType,
        Product,
        SettlementType,
        TimeInForce,
        TradingState,
        TrailingOffsetType,
        TriggerType,
    )
    from aqp.core.domain.identifiers import (
        AccountId,
        ActorId,
        ClientId,
        ClientOrderId,
        ComponentId,
        ExecAlgorithmId,
        IdentifierScheme,
        IdentifierSet,
        IdentifierValue,
        InstrumentId,
        OrderListId,
        PositionId,
        StrategyId,
        Symbol2,
        TradeId,
        TraderId,
        Venue,
        VenueOrderId,
    )
    from aqp.core.domain.orders import (
        DomainOrder,
        LimitIfTouchedOrder,
        LimitOrder,
        MarketIfTouchedOrder,
        MarketOrder,
        MarketToLimitOrder,
        OrderList,
        StopLimitOrder,
        StopMarketOrder,
        TrailingStopLimitOrder,
        TrailingStopMarketOrder,
    )
except Exception:  # noqa: BLE001 - bootstrap-safe fallback
    # Domain types unavailable (early-boot import). Callers that try to
    # use them get AttributeError; the legacy names above continue to work.
    pass


__all__ = [
    # ----- legacy enums (kept verbatim) -----
    "ACTIVE_STATUSES",
    "AssetClass",
    "DataNormalizationMode",
    "Direction",
    "EventType",
    "Exchange",
    "Interval",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Resolution",
    "SecurityType",
    "TickType",
    # ----- legacy compat-shim classes -----
    "AccountData",
    "Cash",
    "CashBook",
    "OrderData",
    "OrderEvent",
    "OrderRequest",
    "OrderTicket",
    "PositionData",
    "SecurityHolding",
    "Symbol",
    "TradeData",
    # ----- market data / data plane (no domain equivalent) -----
    "BarData",
    "QuoteBar",
    "SubscriptionDataConfig",
    "Tick",
    "TickData",
    "TradeBar",
    # ----- framework value objects (no domain equivalent) -----
    "Event",
    "FillEvent_Msg",
    "MarketEvent",
    "OrderEvent_Msg",
    "PortfolioTarget",
    "Signal",
    "SignalEvent",
    # ----- utilities -----
    "iter_subscriptions",
    "money",
    # ----- domain re-exports (Phase 1-5) -----
    "AccountId",
    "ActorId",
    "AggressorSide",
    "BarAggregation",
    "BookAction",
    "BookType",
    "ClientId",
    "ClientOrderId",
    "ComponentId",
    "ContingencyType",
    "CorporateActionKind",
    "DomainAccountType",
    "DomainAssetClass",
    "DomainOrder",
    "DomainOrderSide",
    "DomainOrderStatus",
    "DomainOrderType",
    "ExecAlgorithmId",
    "FilingType",
    "IdentifierScheme",
    "IdentifierSet",
    "IdentifierValue",
    "IndustryClassificationScheme",
    "InstrumentClass",
    "InstrumentCloseType",
    "InstrumentId",
    "LimitIfTouchedOrder",
    "LimitOrder",
    "LiquiditySide",
    "MarketIfTouchedOrder",
    "MarketOrder",
    "MarketStatus",
    "MarketToLimitOrder",
    "Offset",
    "OmsType",
    "OptionKind",
    "OptionStyle",
    "OrderList",
    "OrderListId",
    "PayReceive",
    "PositionId",
    "PositionSide",
    "PriceType",
    "Product",
    "SettlementType",
    "StopLimitOrder",
    "StopMarketOrder",
    "StrategyId",
    "Symbol2",
    "TimeInForce",
    "TradeId",
    "TraderId",
    "TradingState",
    "TrailingOffsetType",
    "TrailingStopLimitOrder",
    "TrailingStopMarketOrder",
    "TriggerType",
    "Venue",
    "VenueOrderId",
]
