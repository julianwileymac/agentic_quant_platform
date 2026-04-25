"""IBKR real-time 5-second bar feed (``ib-async`` ``reqRealTimeBars``)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from typing import Any

try:
    from ib_async import IB  # type: ignore[import]
    from ib_async import Stock as _IBStock
except ImportError as exc:  # pragma: no cover — optional
    raise ImportError(
        'IBKRDataFeed requires the "ibkr" extra. '
        'Install with: pip install -e ".[ibkr]"'
    ) from exc

from aqp.config import settings
from aqp.core.registry import register
from aqp.core.types import BarData, Exchange, Interval, Symbol
from aqp.observability import get_tracer
from aqp.trading.feeds.base import BaseFeed

logger = logging.getLogger(__name__)
tracer = get_tracer("aqp.live.ibkr_feed")


@register("IBKRDataFeed")
class IBKRDataFeed(BaseFeed):
    """Streams IBKR 5s real-time bars and re-emits them as :class:`BarData`."""

    name = "ibkr-feed"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        exchange: str = "SMART",
        currency: str = "USD",
        connect_timeout: float = 8.0,
    ) -> None:
        super().__init__()
        self.host = host or settings.ibkr_host
        self.port = int(port if port is not None else settings.ibkr_port)
        # Use a dedicated client_id offset so the feed doesn't collide with
        # the brokerage connection.
        base = int(client_id if client_id is not None else settings.ibkr_client_id)
        self.client_id = base + 100
        self.exchange = exchange
        self.currency = currency
        self.connect_timeout = float(connect_timeout)
        self._ib = IB()
        self._queue: asyncio.Queue[BarData] = asyncio.Queue(maxsize=1024)
        self._subscriptions_by_reqid: dict[int, str] = {}
        self._first_bar_symbols: set[str] = set()

    async def connect(self) -> None:
        # NOTE: ``ib_async.util.patchAsyncio()`` (aka ``nest_asyncio.apply``)
        # must not be called here — it corrupts ``anyio``'s backend detection
        # on Python 3.14 and every subsequent sync FastAPI route 500s. The
        # uvicorn loop already provides proper asyncio semantics.
        with tracer.start_as_current_span("ibkr.feed.connect") as span:
            span.set_attribute("net.peer.name", self.host)
            span.set_attribute("net.peer.port", self.port)
            span.set_attribute("aqp.ibkr.client_id", self.client_id)
            if not self._ib.isConnected():
                try:
                    await self._ib.connectAsync(
                        self.host,
                        self.port,
                        clientId=self.client_id,
                        timeout=self.connect_timeout,
                        readonly=True,
                    )
                    logger.info(
                        "ibkr feed connected host=%s port=%s client_id=%s",
                        self.host,
                        self.port,
                        self.client_id,
                    )
                except Exception as exc:
                    span.record_exception(exc)
                    logger.exception(
                        "ibkr feed connect failed host=%s port=%s client_id=%s",
                        self.host,
                        self.port,
                        self.client_id,
                    )
                    raise

    async def disconnect(self) -> None:
        with tracer.start_as_current_span("ibkr.feed.disconnect") as span:
            span.set_attribute("net.peer.name", self.host)
            span.set_attribute("net.peer.port", self.port)
            span.set_attribute("aqp.ibkr.client_id", self.client_id)
            try:
                if self._ib.isConnected():
                    self._ib.disconnect()
                    logger.info(
                        "ibkr feed disconnected host=%s port=%s client_id=%s",
                        self.host,
                        self.port,
                        self.client_id,
                    )
            except Exception as exc:
                span.record_exception(exc)
                logger.exception("ibkr feed disconnect error")

    async def subscribe(self, symbols: Iterable[Symbol]) -> None:
        symbols_list = list(symbols)
        with tracer.start_as_current_span("ibkr.feed.subscribe") as span:
            span.set_attribute("aqp.symbol_count", len(symbols_list))
            if symbols_list:
                span.set_attribute("aqp.symbols", ",".join(s.vt_symbol for s in symbols_list))
            await super().subscribe(symbols_list)
            for s in symbols_list:
                contract = _IBStock(s.ticker, self.exchange, self.currency)
                bars = self._ib.reqRealTimeBars(
                    contract,
                    barSize=5,
                    whatToShow="TRADES",
                    useRTH=False,
                )
                bars.updateEvent += self._make_handler(s)
            logger.info(
                "ibkr feed subscribed symbol_count=%d symbols=%s",
                len(symbols_list),
                ",".join(s.vt_symbol for s in symbols_list),
            )

    async def unsubscribe(self, symbols: Iterable[Symbol]) -> None:
        await super().unsubscribe(symbols)
        # reqRealTimeBars doesn't expose per-symbol cancellation easily; on
        # full session shutdown ``disconnect`` will clean up.

    def _make_handler(self, symbol: Symbol) -> Any:
        def handler(bars: Any, has_new_bar: bool) -> None:
            if not has_new_bar or not bars:
                return
            last = bars[-1]
            try:
                if symbol.vt_symbol not in self._first_bar_symbols:
                    self._first_bar_symbols.add(symbol.vt_symbol)
                    logger.info(
                        "ibkr feed first realtime bar symbol=%s host=%s port=%s client_id=%s",
                        symbol.vt_symbol,
                        self.host,
                        self.port,
                        self.client_id,
                    )
                self._queue.put_nowait(
                    BarData(
                        symbol=symbol,
                        timestamp=last.time if hasattr(last, "time") else datetime.utcnow(),
                        open=float(last.open_),
                        high=float(last.high),
                        low=float(last.low),
                        close=float(last.close),
                        volume=float(last.volume),
                        # ``reqRealTimeBars`` emits exactly 5-second bars.  We used
                        # to mislabel this as ``FIVE_MINUTE`` which broke any
                        # downstream aggregation that relied on the interval.
                        interval=Interval.FIVE_SECOND,
                    )
                )
            except Exception:
                logger.exception("failed to emit IBKR bar for %s", symbol.vt_symbol)

        return handler

    async def stream(self) -> AsyncIterator[BarData]:
        while True:
            yield await self._queue.get()

    @staticmethod
    def _exchange() -> Exchange:
        return Exchange.NASDAQ
