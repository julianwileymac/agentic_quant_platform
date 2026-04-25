"""Alpaca real-time bar feed (``alpaca-py`` ``StockDataStream``)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from typing import Any

try:
    from alpaca.data.live.stock import StockDataStream  # type: ignore[import]
except ImportError as exc:  # pragma: no cover — optional
    raise ImportError(
        'AlpacaDataFeed requires the "alpaca" extra. '
        'Install with: pip install -e ".[alpaca]"'
    ) from exc

import contextlib

from aqp.config import settings
from aqp.core.registry import register
from aqp.core.types import BarData, Exchange, Interval, Symbol
from aqp.trading.feeds.base import BaseFeed

logger = logging.getLogger(__name__)


@register("AlpacaDataFeed")
class AlpacaDataFeed(BaseFeed):
    """Consumes 1-minute (or real-time) bars from Alpaca into :class:`BarData`."""

    name = "alpaca-feed"

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        subscription: str = "iex",
        feed_interval: str = "1m",
    ) -> None:
        super().__init__()
        self.api_key = api_key or settings.alpaca_api_key
        self.secret_key = secret_key or settings.alpaca_secret_key
        self.subscription = subscription
        self.feed_interval = feed_interval
        if not (self.api_key and self.secret_key):
            raise ValueError("AlpacaDataFeed requires AQP_ALPACA_API_KEY + AQP_ALPACA_SECRET_KEY")
        self._stream: StockDataStream | None = None
        self._queue: asyncio.Queue[BarData] = asyncio.Queue(maxsize=1024)
        self._stream_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        if self._stream is None:
            self._stream = StockDataStream(self.api_key, self.secret_key, feed=self.subscription)

    async def disconnect(self) -> None:
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stream_task
        if self._stream is not None:
            try:
                await self._stream.stop_ws()
            except Exception:
                logger.exception("alpaca stream stop failed")
            self._stream = None

    async def subscribe(self, symbols: Iterable[Symbol]) -> None:
        await super().subscribe(symbols)
        if self._stream is None:
            return
        tickers = [s.ticker for s in symbols]
        self._stream.subscribe_bars(self._on_bar, *tickers)
        if self._stream_task is None:
            self._stream_task = asyncio.create_task(self._stream._run_forever())  # noqa: SLF001

    async def unsubscribe(self, symbols: Iterable[Symbol]) -> None:
        await super().unsubscribe(symbols)
        if self._stream is None:
            return
        for s in symbols:
            try:
                self._stream.unsubscribe_bars(s.ticker)
            except Exception:
                logger.exception("alpaca unsubscribe failed for %s", s.ticker)

    async def _on_bar(self, bar: Any) -> None:
        try:
            await self._queue.put(
                BarData(
                    symbol=Symbol(ticker=str(bar.symbol), exchange=Exchange.NASDAQ),
                    timestamp=bar.timestamp or datetime.utcnow(),
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume),
                    interval=Interval(self.feed_interval) if self.feed_interval in {i.value for i in Interval} else Interval.MINUTE,
                )
            )
        except Exception:
            logger.exception("alpaca on_bar handler failed")

    async def stream(self) -> AsyncIterator[BarData]:
        while True:
            yield await self._queue.get()
