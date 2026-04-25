"""Polling feed for REST venues that don't expose WebSockets.

Makes a ``GET /quotes?symbols=...`` style call every ``poll_seconds`` and
emits a synthetic :class:`BarData` per subscribed symbol where the OHLC
values collapse to the last quote. Good enough for a heartbeat tick to a
mean-reversion strategy.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from typing import Any

import httpx

from aqp.core.registry import register
from aqp.core.types import BarData, Exchange, Interval, Symbol
from aqp.trading.feeds.base import BaseFeed

logger = logging.getLogger(__name__)


@register("RestPollingFeed")
class RestPollingFeed(BaseFeed):
    """Generic polling feed usable with any REST quote endpoint.

    The caller must subclass to override :meth:`_fetch_quotes`, OR pass a
    callable producing ``[(ticker, price), ...]`` tuples.
    """

    name = "rest-poll"

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        poll_seconds: float = 5.0,
        quote_path: str = "/quotes",
        interval: str = "1m",
        custom_fetch: Any = None,
    ) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.poll_seconds = float(poll_seconds)
        self.quote_path = quote_path
        self.interval = interval
        self._custom_fetch = custom_fetch
        self._client: httpx.AsyncClient | None = None
        self._queue: asyncio.Queue[BarData] = asyncio.Queue(maxsize=1024)
        self._poll_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=10.0)
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll())

    async def disconnect(self) -> None:
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._poll_task
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def subscribe(self, symbols: Iterable[Symbol]) -> None:
        await super().subscribe(symbols)

    async def unsubscribe(self, symbols: Iterable[Symbol]) -> None:
        await super().unsubscribe(symbols)

    # -------------------------------- polling ----------------------------

    async def _poll(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.poll_seconds)
                if not self._subscriptions:
                    continue
                quotes = await self._fetch_quotes(sorted(self._subscriptions))
                for ticker, price in quotes:
                    await self._emit(ticker, price)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("rest-poll loop error")
                await asyncio.sleep(self.poll_seconds)

    async def _fetch_quotes(self, vt_symbols: list[str]) -> list[tuple[str, float]]:
        if self._custom_fetch is not None:
            result = await self._custom_fetch(vt_symbols)  # type: ignore[misc]
            return list(result)
        assert self._client is not None
        tickers = ",".join(vt_symbol.split(".")[0] for vt_symbol in vt_symbols)
        resp = await self._client.get(self.quote_path, params={"symbols": tickers})
        resp.raise_for_status()
        payload = resp.json()
        quotes = _extract_quotes(payload)
        return [(vt_symbol, quotes.get(vt_symbol.split(".")[0], 0.0)) for vt_symbol in vt_symbols]

    async def _emit(self, vt_symbol: str, price: float) -> None:
        if price <= 0:
            return
        ticker, _, exch = vt_symbol.partition(".")
        try:
            exchange = Exchange(exch) if exch else Exchange.NASDAQ
        except ValueError:
            exchange = Exchange.NASDAQ
        bar = BarData(
            symbol=Symbol(ticker=ticker, exchange=exchange),
            timestamp=datetime.utcnow(),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0.0,
            interval=Interval(self.interval) if self.interval in {i.value for i in Interval} else Interval.MINUTE,
        )
        await self._queue.put(bar)

    async def stream(self) -> AsyncIterator[BarData]:
        while True:
            yield await self._queue.get()


def _extract_quotes(payload: Any) -> dict[str, float]:
    """Best-effort Tradier-style and generic quote parser."""
    if not isinstance(payload, dict):
        return {}
    # Tradier shape: {"quotes": {"quote": [ {"symbol": "AAPL", "last": 187.5}, ... ]}}
    block = payload.get("quotes")
    if isinstance(block, dict):
        q = block.get("quote")
        if isinstance(q, list):
            return {str(item.get("symbol")): float(item.get("last") or 0.0) for item in q}
        if isinstance(q, dict):
            return {str(q.get("symbol")): float(q.get("last") or 0.0)}
    # Generic list shape: [{"symbol": "AAPL", "price": 187.5}, ...]
    if isinstance(payload, list):
        out: dict[str, float] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            sym = item.get("symbol")
            price = item.get("price") or item.get("last")
            if sym and price is not None:
                out[str(sym)] = float(price)
        return out
    return {}
