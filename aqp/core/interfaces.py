"""Core interfaces — Lean-style strict contracts so backtest ≡ live.

Each interface is a narrow ABC. Implementations live elsewhere in the package
(e.g. ``aqp.backtest.broker_sim.SimulatedBrokerage`` implements ``IBrokerage``).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable, Iterator
from datetime import datetime
from typing import Any, Generic, TypeVar

import pandas as pd

from aqp.core.types import (
    AccountData,
    BarData,
    OrderData,
    OrderEvent,
    OrderRequest,
    OrderTicket,
    PortfolioTarget,
    PositionData,
    Signal,
    SubscriptionDataConfig,
    Symbol,
)

T = TypeVar("T")


class IHistoryProvider(ABC):
    """Reads historical market data. Used by backtest engines and research tools."""

    @abstractmethod
    def get_bars(
        self,
        symbols: Iterable[Symbol],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return a tidy DataFrame with columns: ``timestamp, vt_symbol, open, high, low, close, volume``."""


class IDataQueueHandler(ABC):
    """Streams live market data events. Same shape as backtest replay for parity."""

    @abstractmethod
    def subscribe(self, symbols: Iterable[Symbol]) -> None: ...

    @abstractmethod
    def next_event(self) -> BarData | None: ...


class IBrokerage(ABC):
    """Uniform venue adapter — same surface for simulator, paper, and live."""

    name: str = "brokerage"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def submit_order(self, request: OrderRequest) -> OrderData: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def query_positions(self) -> list[PositionData]: ...

    @abstractmethod
    def query_account(self) -> AccountData: ...


class IAsyncBrokerage(ABC):
    """Async superset used by the live/paper trading engine.

    Concrete paper/live adapters (Alpaca, IBKR, Tradier, ...) implement
    *both* :class:`IBrokerage` and this mixin so they remain pluggable into
    the sync backtest engine while allowing the async trading session to
    avoid blocking network calls.
    """

    name: str = "async_brokerage"

    @abstractmethod
    async def connect_async(self) -> None: ...

    @abstractmethod
    async def disconnect_async(self) -> None: ...

    @abstractmethod
    async def submit_order_async(self, request: OrderRequest) -> OrderData: ...

    @abstractmethod
    async def cancel_order_async(self, order_id: str) -> bool: ...

    @abstractmethod
    async def query_positions_async(self) -> list[PositionData]: ...

    @abstractmethod
    async def query_account_async(self) -> AccountData: ...

    @abstractmethod
    def stream_order_updates(self) -> AsyncIterator[OrderData]:
        """Async iterator yielding :class:`OrderData` updates (fills, cancels, rejections)."""


class IMarketDataFeed(ABC):
    """Async market-data feed — the streaming analogue of :class:`IHistoryProvider`.

    Paper/live sessions consume a feed by iterating ``async for bar in feed.stream(symbols): ...``.
    A feed may emit one bar per symbol per interval (most common) or one at a time.
    """

    name: str = "feed"

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def subscribe(self, symbols: Iterable[Symbol]) -> None: ...

    @abstractmethod
    async def unsubscribe(self, symbols: Iterable[Symbol]) -> None: ...

    @abstractmethod
    def stream(self) -> AsyncIterator[BarData]:
        """Async iterator yielding :class:`BarData` as they arrive."""


class IUniverseSelectionModel(ABC):
    """Lean stage 1 — decide which symbols are tradable right now."""

    @abstractmethod
    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]: ...


class IAlphaModel(ABC):
    """Core reasoning layer: generates standardized Insight (Signal) objects."""

    @abstractmethod
    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        """Produce a list of alpha insights for the given market slice."""
        ...


class IPortfolioConstructionModel(ABC):
    """Strategy layer: determines target position sizes from alpha insights."""

    @abstractmethod
    def construct(
        self,
        signals: list[Signal],
        context: dict[str, Any],
    ) -> list[PortfolioTarget]:
        """Translate alpha insights into target weights/quantities."""
        ...


class IRiskManagementModel(ABC):
    """Constraint layer: intercepts and adjusts portfolio targets."""

    @abstractmethod
    def evaluate(
        self,
        targets: list[PortfolioTarget],
        context: dict[str, Any],
    ) -> list[PortfolioTarget]:
        """Apply risk limits (drawdown, exposure, etc.) to target set."""
        ...


class IExecutionModel(ABC):
    """Deterministic layer: translates risk-adjusted targets into broker orders."""

    @abstractmethod
    def execute(
        self,
        targets: list[PortfolioTarget],
        context: dict[str, Any],
    ) -> list[OrderRequest]:
        """Optimize entry/exit and generate broker-ready order requests."""
        ...


class IStrategy(ABC):
    """High-level strategy contract. Composes the 5-stage framework."""

    strategy_id: str

    @abstractmethod
    def on_bar(self, bar: BarData, context: dict[str, Any]) -> Iterator[OrderRequest]: ...

    @abstractmethod
    def on_order_update(self, order: OrderData) -> None: ...


class ITimeProvider(ABC):
    """Abstracted clock so backtest and live use the same code path (Lean pattern)."""

    @abstractmethod
    def now(self) -> datetime: ...


class IFeatureStore(ABC):
    """Returns precomputed features for a ``(symbol, timestamp)`` tuple."""

    @abstractmethod
    def get_features(
        self,
        symbol: Symbol,
        timestamp: datetime,
        feature_set: str,
    ) -> dict[str, float]: ...


class IModel(ABC):
    """Qlib-style narrow ML model contract."""

    @abstractmethod
    def fit(self, dataset: Any, **kwargs: Any) -> IModel: ...

    @abstractmethod
    def predict(self, dataset: Any, **kwargs: Any) -> pd.Series: ...


# ---------------------------------------------------------------------------
# Lean engine-layer interfaces (transaction handler, result handler, etc.)
# ---------------------------------------------------------------------------


class ITransactionHandler(ABC):
    """Central order pipeline (Lean ``BrokerageTransactionHandler``).

    Translates ``OrderRequest`` into ``OrderTicket`` objects, routes them
    to the brokerage, and publishes ``OrderEvent`` updates as they arrive.
    Implementations may be synchronous for the backtest engine or async
    for the live/paper engines.
    """

    @abstractmethod
    def submit_ticket(self, request: OrderRequest) -> OrderTicket: ...

    @abstractmethod
    def cancel_ticket(self, order_id: str) -> bool: ...

    @abstractmethod
    def tickets(self) -> list[OrderTicket]: ...

    @abstractmethod
    def process_events(self) -> AsyncIterator[OrderEvent]: ...


class IResultHandler(ABC):
    """Sampling/charting/statistics sink (Lean ``BacktestingResultHandler``)."""

    @abstractmethod
    def on_sample(
        self,
        timestamp: datetime,
        equity: float,
        cash: float,
        positions: list[PositionData],
    ) -> None: ...

    @abstractmethod
    def on_trade(self, ticket: OrderTicket, event: OrderEvent) -> None: ...

    @abstractmethod
    def on_order(self, ticket: OrderTicket) -> None: ...

    @abstractmethod
    def on_log(self, level: str, message: str) -> None: ...

    @abstractmethod
    def finalize(self) -> dict[str, Any]: ...


class IIndicator(ABC, Generic[T]):
    """Incremental indicator contract. The canonical implementation lives in
    :mod:`aqp.core.indicators`; this exists so other modules can type-annotate
    without pulling the concrete base."""

    name: str = "indicator"

    @property
    @abstractmethod
    def is_ready(self) -> bool: ...

    @abstractmethod
    def update(self, value: T, timestamp: datetime | None = None) -> float: ...

    @abstractmethod
    def reset(self) -> None: ...


class IOrderTicket(ABC):
    """Protocol for :class:`aqp.core.types.OrderTicket`-like handles."""

    @property
    @abstractmethod
    def order_id(self) -> str: ...

    @abstractmethod
    def is_active(self) -> bool: ...

    @abstractmethod
    def append_event(self, event: OrderEvent) -> None: ...


class IExchangeHoursDatabase(ABC):
    """Protocol for market-hours lookups."""

    @abstractmethod
    def is_open(self, exchange: str, utc_dt: datetime) -> bool: ...

    @abstractmethod
    def next_open(self, exchange: str, utc_dt: datetime) -> datetime | None: ...


class ISubscriptionManager(ABC):
    """Routes a ``SubscriptionDataConfig`` to a concrete data source."""

    @abstractmethod
    def add(self, cfg: SubscriptionDataConfig) -> None: ...

    @abstractmethod
    def remove(self, cfg: SubscriptionDataConfig) -> None: ...

    @abstractmethod
    def list(self) -> list[SubscriptionDataConfig]: ...

    @abstractmethod
    def history_provider(self, cfg: SubscriptionDataConfig) -> IHistoryProvider: ...
