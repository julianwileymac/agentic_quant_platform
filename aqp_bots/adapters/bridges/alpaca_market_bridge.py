"""Bridge from the legacy Alpaca WS ingester onto :class:`MarketDataAdapter`.

The existing :mod:`aqp.streaming.ingesters.alpaca` publishes events to
Kafka. This bridge tees a copy onto the kernel's local bus so a
kernel-mode bot can consume without changing the Kafka pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from aqp_bots.adapters.protocol import (
    AdapterCapability,
    AdapterUnavailable,
    MarketDataAdapter,
    Subscription,
)
from aqp_bots.schemas.market import MarketEvent, Quote, Tick

logger = logging.getLogger(__name__)


class AlpacaBridgeMarketDataAdapter(MarketDataAdapter):
    """Bridge over the existing Alpaca WS ingester.

    Conceptually identical to the FIX/REST adapters but reuses the
    AQP Alpaca client + subscription state so we don't double-pay
    the WebSocket connection budget.
    """

    adapter_kind = "alpaca_bridge"
    adapter_alias = "alpaca_bridge"
    capability = AdapterCapability(
        venue="alpaca",
        asset_classes=("equity", "spot_crypto"),
        supports_streaming=True,
    )

    def __init__(self, *, paper: bool = True) -> None:
        self._paper = paper
        self._client: Any | None = None
        self._queue: asyncio.Queue[MarketEvent] = asyncio.Queue(maxsize=8192)
        self._subs: list[Subscription] = []
        self._closed = False

    async def connect(self) -> None:
        try:
            from alpaca.data.live.stock import StockDataStream  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AdapterUnavailable(
                "alpaca-py required for AlpacaBridgeMarketDataAdapter"
            ) from exc
        # Credentials resolved via existing AQP credential plumbing.
        try:
            from aqp.config import settings

            api_key = getattr(settings, "alpaca_api_key", None)
            api_secret = getattr(settings, "alpaca_api_secret", None)
        except Exception:  # noqa: BLE001
            api_key = api_secret = None
        if not api_key or not api_secret:
            raise AdapterUnavailable("Alpaca credentials not configured")
        self._client = StockDataStream(api_key, api_secret)

    async def subscribe(self, sub: Subscription) -> None:
        if self._client is None:
            await self.connect()
        self._subs.append(sub)
        try:
            if "trades" in sub.channels:
                self._client.subscribe_trades(  # type: ignore[union-attr]
                    self._on_trade, sub.symbol
                )
            if "quotes" in sub.channels:
                self._client.subscribe_quotes(  # type: ignore[union-attr]
                    self._on_quote, sub.symbol
                )
        except Exception:  # noqa: BLE001
            logger.exception("alpaca subscribe failed for %s", sub.symbol)
            raise

    async def stream(self) -> AsyncIterator[MarketEvent]:
        if self._client is None:
            return
        # Run the alpaca-py event loop in the background and drain its
        # callbacks into our queue.
        task = asyncio.create_task(self._run_client())
        try:
            while not self._closed:
                evt = await self._queue.get()
                yield evt
        finally:
            task.cancel()
            try:
                await task
            except Exception:  # noqa: BLE001
                pass

    async def aclose(self) -> None:
        self._closed = True
        if self._client is not None:
            try:
                await self._client.stop_ws()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _run_client(self) -> None:
        try:
            await self._client._run_forever()  # type: ignore[union-attr]
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("alpaca ws loop terminated")

    async def _on_trade(self, trade: Any) -> None:
        evt = Tick(
            venue="alpaca",
            symbol=str(getattr(trade, "symbol", "")),
            price=Decimal(str(getattr(trade, "price", 0))),
            size=Decimal(str(getattr(trade, "size", 0))),
            exchange_ts_ns=int(getattr(trade, "timestamp", 0) or 0),
            ingress_ts_ns=time.time_ns(),
            trade_id=str(getattr(trade, "id", "")),
        )
        await self._queue.put(evt)

    async def _on_quote(self, quote: Any) -> None:
        evt = Quote(
            venue="alpaca",
            symbol=str(getattr(quote, "symbol", "")),
            bid_px=Decimal(str(getattr(quote, "bid_price", 0))),
            bid_sz=Decimal(str(getattr(quote, "bid_size", 0))),
            ask_px=Decimal(str(getattr(quote, "ask_price", 0))),
            ask_sz=Decimal(str(getattr(quote, "ask_size", 0))),
            exchange_ts_ns=int(getattr(quote, "timestamp", 0) or 0),
            ingress_ts_ns=time.time_ns(),
        )
        await self._queue.put(evt)


__all__ = ["AlpacaBridgeMarketDataAdapter"]
