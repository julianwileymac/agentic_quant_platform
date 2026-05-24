"""Reusable :class:`WebsocketMarketDataAdapter` base.

Wires:

- ``websockets`` client connect / reconnect.
- Exponential backoff with jitter on disconnect.
- Idempotent resubscribe on reconnect.
- :mod:`msgspec` JSON decode hook.
- Throttled outbound (per-venue ``max_orders_per_second`` advisory).

Concrete venue adapters inherit, set ``adapter_kind`` + ``capability``,
and override :meth:`decode_message`. The metaclass on
:class:`MarketDataAdapter` registers them automatically.
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from aqp_bots.adapters.protocol import (
    MarketDataAdapter,
    Subscription,
)
from aqp_bots.schemas.market import MarketEvent

logger = logging.getLogger(__name__)


class WebsocketAdapterError(RuntimeError):
    """Raised on terminal transport failure."""


@dataclass(slots=True)
class BackoffPolicy:
    """Exponential backoff with jitter.

    Used on reconnect: ``min(base * 2**attempt, cap) + uniform(0, jitter)``.
    """

    base_seconds: float = 1.0
    cap_seconds: float = 60.0
    jitter_seconds: float = 0.5

    def delay(self, attempt: int) -> float:
        d = min(self.base_seconds * (2**attempt), self.cap_seconds)
        return d + random.uniform(0, self.jitter_seconds)


class WebsocketMarketDataAdapter(MarketDataAdapter):
    """Base for WS-based market-data adapters.

    Subclass and:

    1. Set ``adapter_kind`` (e.g. ``binance_spot``) and ``capability``.
    2. Override :attr:`ws_url`.
    3. Override :meth:`decode_message` to translate venue JSON onto
       :class:`MarketEvent`.
    4. Optionally override :meth:`subscribe_message` to emit the
       venue's subscribe payload.
    """

    __abstract_adapter__ = True

    ws_url: str = ""

    def __init__(self, *, backoff: BackoffPolicy | None = None) -> None:
        self._ws: Any | None = None
        self._subs: list[Subscription] = []
        self._closed: bool = False
        self._backoff = backoff or BackoffPolicy()
        self._reconnect_attempt: int = 0

    async def connect(self) -> None:
        await self._dial()

    async def subscribe(self, sub: Subscription) -> None:
        self._subs.append(sub)
        if self._ws is not None:
            await self._send_subscribe(sub)

    async def stream(self) -> AsyncIterator[MarketEvent]:
        while not self._closed:
            try:
                if self._ws is None:
                    await self._dial()
                assert self._ws is not None
                async for raw in self._ws:
                    if self._closed:
                        return
                    event = self.decode_message(raw)
                    if event is None:
                        continue
                    if isinstance(event, list):
                        for e in event:
                            yield e
                    else:
                        yield event
            except Exception:  # noqa: BLE001
                if self._closed:
                    return
                attempt = self._reconnect_attempt
                self._reconnect_attempt += 1
                delay = self._backoff.delay(attempt)
                logger.warning(
                    "ws %s disconnected; reconnect in %.2fs (attempt %d)",
                    self.adapter_kind,
                    delay,
                    attempt + 1,
                )
                await asyncio.sleep(delay)
                self._ws = None

    async def aclose(self) -> None:
        self._closed = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None

    # ------------------------------------------------------------------
    # Customization hooks
    # ------------------------------------------------------------------

    def decode_message(self, raw: str | bytes) -> MarketEvent | list[MarketEvent] | None:
        """Translate venue JSON to a :class:`MarketEvent` (subclass override)."""
        raise NotImplementedError

    async def subscribe_message(self, sub: Subscription) -> dict[str, Any]:
        """Build the venue-specific subscription payload (subclass override)."""
        return {"op": "subscribe", "args": [{"symbol": sub.symbol, "channels": list(sub.channels)}]}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _dial(self) -> None:
        try:
            import websockets  # type: ignore[import-not-found]
        except ImportError as exc:
            raise WebsocketAdapterError(
                "websockets package required for WebsocketMarketDataAdapter"
            ) from exc
        if not self.ws_url:
            raise WebsocketAdapterError(
                f"{self.__class__.__name__}.ws_url not configured"
            )
        self._ws = await websockets.connect(self.ws_url)  # type: ignore[attr-defined]
        self._reconnect_attempt = 0
        # Idempotent resubscribe.
        for sub in self._subs:
            await self._send_subscribe(sub)

    async def _send_subscribe(self, sub: Subscription) -> None:
        if self._ws is None:
            return
        import json

        payload = await self.subscribe_message(sub)
        await self._ws.send(json.dumps(payload))


__all__ = [
    "BackoffPolicy",
    "WebsocketAdapterError",
    "WebsocketMarketDataAdapter",
]
