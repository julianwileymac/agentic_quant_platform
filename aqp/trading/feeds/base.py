"""Shared feed helpers and a deterministic replay feed used by tests / dry-runs."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any

import pandas as pd

from aqp.core.interfaces import IMarketDataFeed
from aqp.core.registry import register
from aqp.core.types import BarData, Exchange, Interval, Symbol

logger = logging.getLogger(__name__)


class BaseFeed(IMarketDataFeed):
    """Small shim that owns the set of subscribed ``vt_symbol``s.

    Concrete adapters should implement :meth:`stream` as an async generator
    that yields :class:`BarData`.
    """

    def __init__(self) -> None:
        self._subscriptions: set[str] = set()

    async def connect(self) -> None:  # pragma: no cover — simple default
        return

    async def disconnect(self) -> None:  # pragma: no cover
        return

    async def subscribe(self, symbols: Iterable[Symbol]) -> None:
        for s in symbols:
            self._subscriptions.add(s.vt_symbol)

    async def unsubscribe(self, symbols: Iterable[Symbol]) -> None:
        for s in symbols:
            self._subscriptions.discard(s.vt_symbol)

    def subscribed_symbols(self) -> list[str]:
        return sorted(self._subscriptions)


@register("DeterministicReplayFeed")
class DeterministicReplayFeed(BaseFeed):
    """Replays a tidy bars DataFrame at a configurable cadence.

    Used by::

    - the ``aqp paper run --dry-run`` CLI path so users can smoke-test broker
      adapters against historical data without a live subscription;
    - ``tests/test_trading_session.py`` to assert parity vs. the backtest
      event loop.
    """

    name = "replay"

    def __init__(
        self,
        bars: pd.DataFrame,
        cadence_seconds: float = 0.0,
        interval: str = "1d",
    ) -> None:
        super().__init__()
        if not {"timestamp", "vt_symbol", "open", "high", "low", "close", "volume"}.issubset(bars.columns):
            raise ValueError(
                "DeterministicReplayFeed requires tidy bars columns: "
                "timestamp, vt_symbol, open, high, low, close, volume"
            )
        self.bars = bars.copy()
        self.bars["timestamp"] = pd.to_datetime(self.bars["timestamp"])
        self.bars = self.bars.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)
        self.cadence_seconds = float(cadence_seconds)
        try:
            self.interval = Interval(interval)
        except ValueError:
            self.interval = Interval.DAY

    async def stream(self) -> AsyncIterator[BarData]:
        wanted = self._subscriptions or set(self.bars["vt_symbol"].unique().tolist())
        for _, row in self.bars.iterrows():
            if row["vt_symbol"] not in wanted:
                continue
            yield _row_to_bar(row, self.interval)
            if self.cadence_seconds > 0:
                await asyncio.sleep(self.cadence_seconds)
            else:
                # Still yield the event loop so cancellation works.
                await asyncio.sleep(0)


def _row_to_bar(row: pd.Series[Any], interval: Interval) -> BarData:
    ticker, exchange = _parse_vt(row["vt_symbol"])
    return BarData(
        symbol=Symbol(ticker=ticker, exchange=exchange),
        timestamp=row["timestamp"].to_pydatetime() if hasattr(row["timestamp"], "to_pydatetime") else row["timestamp"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        interval=interval,
    )


def _parse_vt(vt: str) -> tuple[str, Exchange]:
    if "." not in vt:
        return vt, Exchange.NASDAQ
    ticker, exch = vt.rsplit(".", 1)
    try:
        return ticker, Exchange(exch)
    except ValueError:
        return ticker, Exchange.NASDAQ
