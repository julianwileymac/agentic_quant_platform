"""Core immutable types — Lean-inspired with vnpy ``vt_symbol`` composite IDs.

This module is the **single source of truth** for every domain value that
flows between the data feeds, strategy stages, brokerages, and the
execution ledger.

The existing public surface (``BarData``, ``OrderRequest``, ``Signal``,
etc.) is preserved to keep backward compatibility; the expansion adds
richer Lean-style types alongside the originals:

- ``SecurityType``, ``Resolution``, ``TickType``, ``DataNormalizationMode``
- ``SubscriptionDataConfig`` — the data-plane routing key
- ``TradeBar`` (alias for ``BarData``) and ``QuoteBar`` (bid/ask OHLC)
- ``Tick`` (alias for ``TickData``)
- ``SecurityHolding`` — extended position linking to ``PortfolioTarget``
- ``Cash`` / ``CashBook`` — multi-currency account accounting
- ``OrderEvent`` / ``OrderTicket`` — stable order handle with event stream
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Exchange(StrEnum):
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
    """Lean-style security type (richer than ``AssetClass``)."""

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
    LONG = "long"
    SHORT = "short"
    NET = "net"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    MARKET_ON_OPEN = "market_on_open"
    MARKET_ON_CLOSE = "market_on_close"
    TRAILING_STOP = "trailing_stop"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    SUBMITTING = "submitting"
    NEW = "new"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


ACTIVE_STATUSES = {OrderStatus.SUBMITTING, OrderStatus.NEW, OrderStatus.PARTIAL}


class Interval(StrEnum):
    """Short-code bar cadence (vnpy style). ``Resolution`` is the Lean-style enum."""

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
    """Lean-style data resolution enum with ``timedelta`` helpers."""

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
    """Lean ``TickType`` — what a tick represents."""

    TRADE = "trade"
    QUOTE = "quote"
    OPEN_INTEREST = "open_interest"


class DataNormalizationMode(StrEnum):
    """How historical prices are adjusted for corporate actions."""

    RAW = "raw"
    ADJUSTED = "adjusted"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """Immutable composite identifier. Mirrors vnpy's ``vt_symbol`` pattern.

    As of the domain-model expansion, :class:`Symbol` is the
    compatibility-preserving facade over
    :class:`aqp.core.domain.identifiers.InstrumentId`. Existing callers
    keep passing ``Symbol`` objects; new code can ``.to_instrument_id()`` to
    get the richer typed value object, or
    :meth:`Symbol.from_instrument_id` to round-trip back.
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
        if "." not in vt:
            return cls(ticker=vt)
        ticker, exch = vt.rsplit(".", 1)
        try:
            exchange = Exchange(exch)
        except ValueError:
            exchange = Exchange.LOCAL
        return cls(ticker=ticker, exchange=exchange)

    def to_instrument_id(self) -> Any:
        """Return an :class:`aqp.core.domain.InstrumentId` equivalent.

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
        """Build a back-compat :class:`Symbol` from a domain :class:`InstrumentId`."""
        ticker = instrument_id.symbol.value if hasattr(instrument_id, "symbol") else str(instrument_id)
        venue = instrument_id.venue.value if hasattr(instrument_id, "venue") else "LOCAL"
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
    """Data-plane routing key.

    Every bar/tick flows into the platform via a ``SubscriptionDataConfig``
    rather than a loose ``(symbol, interval)`` tuple. This matches Lean's
    ``SubscriptionDataConfig`` and lets us attach fill-forward semantics,
    corporate-action normalization, and extended-hours preferences to a
    single immutable key.
    """

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
# Market data (bars, quote bars, ticks)
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
        """Lean parity — ``BaseData.Value`` maps to the close price."""
        return self.close

    @property
    def period(self) -> timedelta:
        """Bar period inferred from ``interval``."""
        return Resolution.from_interval(self.interval).to_timedelta()


# Lean-friendly alias. ``TradeBar`` is the canonical name for the
# "trade-derived OHLCV" concept used elsewhere in the platform.
TradeBar = BarData


@dataclass
class QuoteBar:
    """Bid/ask OHLC bar (the Lean ``QuoteBar``)."""

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
# Orders, tickets, events
# ---------------------------------------------------------------------------


@dataclass
class OrderRequest:
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


@dataclass
class OrderData:
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


@dataclass
class TradeData:
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


@dataclass
class OrderEvent:
    """Order state-transition / fill message (Lean ``OrderEvent``).

    Every transition that touches an order — partial fill, full fill,
    cancellation, rejection — emits one ``OrderEvent``. An ``OrderTicket``
    aggregates the running event log.
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

    Application code keeps the ticket around instead of the mutable
    ``OrderData`` so it can observe the order's full lifecycle without
    racing the brokerage.
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
    symbol: Symbol
    direction: Direction
    quantity: float
    average_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @property
    def notional(self) -> float:
        return self.quantity * self.average_price


@dataclass
class SecurityHolding:
    """Extended Lean-style position record.

    Carries everything ``PositionData`` tracks plus:

    - ``fees`` accumulated
    - ``last_trade_ts`` to drive trailing-stop risk models
    - ``target`` — a reference to the last ``PortfolioTarget`` emitted for
      this security so the framework stages can reason about it
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

    ``conversion_rate`` is the cross rate against the account base currency
    (``1.0`` when ``currency`` *is* the base).
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

    Keys are currency codes (``"USD"``, ``"EUR"``, ``"BTC"``, …); values
    are ``Cash`` objects. ``total_value_in_account_currency`` converts every
    entry using its ``conversion_rate`` and returns the aggregate.
    """

    def __init__(self, account_currency: str = "USD", initial: dict[str, Cash] | None = None) -> None:
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
    account_id: str
    cash: float
    equity: float
    margin_used: float = 0.0
    currency: str = "USD"
    updated_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Framework value objects
# ---------------------------------------------------------------------------


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
