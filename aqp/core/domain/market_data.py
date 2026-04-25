"""Rich market-data primitives (bars, quotes, trades, order books, mark/index prices).

Extends the legacy ``BarData``/``QuoteBar``/``TickData`` from
:mod:`aqp.core.types` with the full nautilus_trader + vnpy catalog:

- :class:`BarSpecification` / :class:`BarType` — first-class descriptor for
  "30-minute bars aggregated on the mid price from venue ABC".
- :class:`QuoteTick` (L1 bid/ask snapshot), :class:`TradeTick` (with aggressor
  side and liquidity classification), :class:`TickSnapshot` (vnpy 5-level).
- :class:`OrderBook` + :class:`OrderBookDelta` + :class:`BookLevel` +
  :class:`BookOrder` — L1/L2/L3 microstructure.
- :class:`MarkPriceUpdate` / :class:`IndexPriceUpdate` /
  :class:`FundingRateUpdate` / :class:`ForwardPrice` — derivatives mark-to-
  model primitives.
- :class:`InstrumentStatus` / :class:`InstrumentClose` — exchange/session
  lifecycle messages.
- :class:`RichSlice` — superset of :class:`aqp.core.slice.Slice` that carries
  the new buckets (order books, mark prices, funding rates, news, filings)
  while remaining duck-compatible with the legacy shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from aqp.core.domain.enums import (
    AggressorSide,
    BarAggregation,
    BookAction,
    BookType,
    InstrumentCloseType,
    LiquiditySide,
    MarketStatus,
    OrderSide,
    PriceType,
)
from aqp.core.domain.identifiers import InstrumentId, TradeId


# ---------------------------------------------------------------------------
# Bar descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BarSpecification:
    """Cadence + basis descriptor shared by every bar in a stream.

    ``step`` = how many units of ``aggregation`` per bar; ``price_type`` = the
    price stream the aggregation runs on (BID/ASK/MID/LAST/MARK).
    """

    step: int
    aggregation: BarAggregation
    price_type: PriceType = PriceType.LAST

    def __str__(self) -> str:
        return f"{self.step}-{self.aggregation.value}-{self.price_type.value}"

    @property
    def is_time_based(self) -> bool:
        return self.aggregation in {
            BarAggregation.MILLISECOND,
            BarAggregation.SECOND,
            BarAggregation.MINUTE,
            BarAggregation.HOUR,
            BarAggregation.DAY,
            BarAggregation.WEEK,
            BarAggregation.MONTH,
        }

    @property
    def timedelta(self) -> timedelta | None:
        """Approximate wall-clock step for time-based bars."""
        unit_map = {
            BarAggregation.MILLISECOND: timedelta(milliseconds=1),
            BarAggregation.SECOND: timedelta(seconds=1),
            BarAggregation.MINUTE: timedelta(minutes=1),
            BarAggregation.HOUR: timedelta(hours=1),
            BarAggregation.DAY: timedelta(days=1),
            BarAggregation.WEEK: timedelta(weeks=1),
            BarAggregation.MONTH: timedelta(days=30),
        }
        unit = unit_map.get(self.aggregation)
        return unit * self.step if unit else None


@dataclass(frozen=True, slots=True)
class BarType:
    """Fully-qualified bar stream ``(instrument_id, spec, aggregation_source)``."""

    instrument_id: InstrumentId
    spec: BarSpecification
    aggregation_source: str = "external"  # external | internal

    def __str__(self) -> str:
        return f"{self.instrument_id}@{self.spec}"


# ---------------------------------------------------------------------------
# Tick primitives
# ---------------------------------------------------------------------------


@dataclass
class QuoteTick:
    """Top-of-book (L1) bid/ask snapshot."""

    instrument_id: InstrumentId
    bid_price: Decimal
    ask_price: Decimal
    bid_size: Decimal
    ask_size: Decimal
    ts_event: datetime
    ts_init: datetime | None = None

    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price + self.ask_price) / 2

    @property
    def spread(self) -> Decimal:
        return self.ask_price - self.bid_price


@dataclass
class TradeTick:
    """A single executed trade with microstructure annotations."""

    instrument_id: InstrumentId
    price: Decimal
    size: Decimal
    aggressor_side: AggressorSide
    trade_id: TradeId
    liquidity_side: LiquiditySide = LiquiditySide.NONE
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None


@dataclass
class TickSnapshot:
    """vnpy-parity 5-level depth snapshot.

    Extends the legacy :class:`aqp.core.types.TickData` shape (which has only
    L1 fields) with full 5-deep bid/ask ladders plus daily context fields
    (``open_interest``, ``turnover``, ``pre_close``, ``limit_up``,
    ``limit_down``) that Chinese and HK feeds ship by default.
    """

    instrument_id: InstrumentId
    ts_event: datetime

    last_price: Decimal = Decimal("0")
    last_volume: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    turnover: Decimal = Decimal("0")
    open_interest: Decimal = Decimal("0")

    open_price: Decimal = Decimal("0")
    high_price: Decimal = Decimal("0")
    low_price: Decimal = Decimal("0")
    pre_close: Decimal = Decimal("0")
    limit_up: Decimal = Decimal("0")
    limit_down: Decimal = Decimal("0")

    bid_price_1: Decimal = Decimal("0")
    bid_price_2: Decimal = Decimal("0")
    bid_price_3: Decimal = Decimal("0")
    bid_price_4: Decimal = Decimal("0")
    bid_price_5: Decimal = Decimal("0")

    ask_price_1: Decimal = Decimal("0")
    ask_price_2: Decimal = Decimal("0")
    ask_price_3: Decimal = Decimal("0")
    ask_price_4: Decimal = Decimal("0")
    ask_price_5: Decimal = Decimal("0")

    bid_volume_1: Decimal = Decimal("0")
    bid_volume_2: Decimal = Decimal("0")
    bid_volume_3: Decimal = Decimal("0")
    bid_volume_4: Decimal = Decimal("0")
    bid_volume_5: Decimal = Decimal("0")

    ask_volume_1: Decimal = Decimal("0")
    ask_volume_2: Decimal = Decimal("0")
    ask_volume_3: Decimal = Decimal("0")
    ask_volume_4: Decimal = Decimal("0")
    ask_volume_5: Decimal = Decimal("0")

    local_ts: datetime | None = None


# ---------------------------------------------------------------------------
# Order book
# ---------------------------------------------------------------------------


@dataclass
class BookOrder:
    """An L3 order-book entry (price + size + order_id + side)."""

    side: OrderSide
    price: Decimal
    size: Decimal
    order_id: str | None = None


@dataclass
class BookLevel:
    """An L2 price level (aggregated across orders at that price)."""

    side: OrderSide
    price: Decimal
    size: Decimal
    order_count: int = 0
    orders: list[BookOrder] = field(default_factory=list)


@dataclass
class OrderBookDelta:
    """Single delta into an order book (ADD/UPDATE/DELETE/CLEAR)."""

    instrument_id: InstrumentId
    action: BookAction
    side: OrderSide
    price: Decimal
    size: Decimal
    order_id: str | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None
    flags: int = 0


@dataclass
class OrderBookDeltas:
    """A batch of :class:`OrderBookDelta` objects to apply atomically."""

    instrument_id: InstrumentId
    deltas: list[OrderBookDelta]
    ts_event: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrderBook:
    """In-memory order book (L1/L2/L3) for an instrument."""

    instrument_id: InstrumentId
    book_type: BookType = BookType.L2_MBP
    bids: list[BookLevel] = field(default_factory=list)
    asks: list[BookLevel] = field(default_factory=list)
    sequence: int = 0
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None

    @property
    def best_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None

    @property
    def best_bid_price(self) -> Decimal | None:
        bb = self.best_bid
        return bb.price if bb else None

    @property
    def best_ask_price(self) -> Decimal | None:
        ba = self.best_ask
        return ba.price if ba else None

    @property
    def spread(self) -> Decimal | None:
        bb, ba = self.best_bid_price, self.best_ask_price
        if bb is None or ba is None:
            return None
        return ba - bb

    @property
    def mid_price(self) -> Decimal | None:
        bb, ba = self.best_bid_price, self.best_ask_price
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2

    def apply_delta(self, delta: OrderBookDelta) -> None:
        """Naïve delta application — kept simple so tests can fuzz it."""
        book = self.bids if delta.side is OrderSide.BUY else self.asks
        if delta.action is BookAction.CLEAR:
            book.clear()
            return
        for idx, level in enumerate(book):
            if level.price == delta.price:
                if delta.action is BookAction.DELETE:
                    book.pop(idx)
                else:
                    level.size = delta.size
                return
        if delta.action in (BookAction.ADD, BookAction.UPDATE):
            book.append(BookLevel(side=delta.side, price=delta.price, size=delta.size))
            book.sort(
                key=lambda lvl: lvl.price,
                reverse=(delta.side is OrderSide.BUY),
            )


# ---------------------------------------------------------------------------
# Mark / index / funding rate / forward
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarkPriceUpdate:
    """Derivatives mark-to-model price (aka "fair price")."""

    instrument_id: InstrumentId
    price: Decimal
    ts_event: datetime
    ts_init: datetime | None = None


@dataclass(frozen=True, slots=True)
class IndexPriceUpdate:
    """Reference index price underlying a derivative."""

    instrument_id: InstrumentId
    price: Decimal
    ts_event: datetime
    ts_init: datetime | None = None


@dataclass(frozen=True, slots=True)
class FundingRateUpdate:
    """Perpetual funding-rate update."""

    instrument_id: InstrumentId
    rate: Decimal
    next_funding_ts: datetime | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None


@dataclass(frozen=True, slots=True)
class ForwardPrice:
    """Forward / strip price at a given maturity."""

    instrument_id: InstrumentId
    maturity: datetime
    price: Decimal
    ts_event: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Instrument lifecycle events
# ---------------------------------------------------------------------------


@dataclass
class InstrumentStatus:
    """Exchange-issued trading-state change."""

    instrument_id: InstrumentId
    status: MarketStatus
    reason: str | None = None
    halt_code: str | None = None
    trading_event: str | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None


@dataclass
class InstrumentClose:
    """Session-close / expiry message."""

    instrument_id: InstrumentId
    close_type: InstrumentCloseType
    close_price: Decimal | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)
    ts_init: datetime | None = None


# ---------------------------------------------------------------------------
# Rich Slice — superset of aqp.core.slice.Slice
# ---------------------------------------------------------------------------


@dataclass
class RichSlice:
    """Immutable snapshot of everything that arrived at a single timestamp.

    Superset of the legacy :class:`aqp.core.slice.Slice`: alongside trade
    bars, quote bars, and ticks it also carries order books, mark prices,
    funding rates, news items, filings, and corporate actions. The legacy
    ``Slice`` continues to work; strategies that want the richer payload
    opt in by accepting ``RichSlice`` instead.
    """

    timestamp: datetime
    bars: dict[str, Any] = field(default_factory=dict)
    quote_bars: dict[str, Any] = field(default_factory=dict)
    ticks: dict[str, list[TickSnapshot]] = field(default_factory=dict)
    quote_ticks: dict[str, QuoteTick] = field(default_factory=dict)
    trade_ticks: dict[str, list[TradeTick]] = field(default_factory=dict)
    order_books: dict[str, OrderBook] = field(default_factory=dict)
    mark_prices: dict[str, MarkPriceUpdate] = field(default_factory=dict)
    index_prices: dict[str, IndexPriceUpdate] = field(default_factory=dict)
    funding_rates: dict[str, FundingRateUpdate] = field(default_factory=dict)
    instrument_statuses: dict[str, InstrumentStatus] = field(default_factory=dict)
    instrument_closes: dict[str, InstrumentClose] = field(default_factory=dict)
    splits: dict[str, Any] = field(default_factory=dict)
    dividends: dict[str, Any] = field(default_factory=dict)
    delistings: dict[str, Any] = field(default_factory=dict)
    news: list[Any] = field(default_factory=list)
    filings: list[Any] = field(default_factory=list)
    economic_observations: list[Any] = field(default_factory=list)

    def __contains__(self, key: str) -> bool:
        return key in self.bars or key in self.quote_bars or key in self.order_books

    def symbols(self) -> list[str]:
        keys: set[str] = set()
        keys.update(self.bars.keys())
        keys.update(self.quote_bars.keys())
        keys.update(self.ticks.keys())
        keys.update(self.order_books.keys())
        keys.update(self.mark_prices.keys())
        keys.update(self.funding_rates.keys())
        return sorted(keys)

    @property
    def is_empty(self) -> bool:
        return not (
            self.bars
            or self.quote_bars
            or self.ticks
            or self.order_books
            or self.news
            or self.filings
        )
