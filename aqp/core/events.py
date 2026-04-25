"""A minimal in-process EventEngine (vnpy-style) for strategy ↔ data ↔ broker wiring.

The real pub/sub across processes is handled by Redis (``aqp.ws.broker``);
this class is for the single-process event loop used by the backtest engine
and for local unit-test wiring.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# --- Event types --------------------------------------------------------

EVENT_BAR = "event.bar"
EVENT_TICK = "event.tick"
EVENT_ORDER = "event.order"
EVENT_TRADE = "event.trade"
EVENT_POSITION = "event.position"
EVENT_ACCOUNT = "event.account"
EVENT_SIGNAL = "event.signal"
EVENT_AGENT = "event.agent"
EVENT_RISK = "event.risk"
EVENT_LOG = "event.log"
EVENT_KILL = "event.kill_switch"


@dataclass
class Event:
    type: str
    payload: Any = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


Handler = Callable[[Event], None]
AsyncHandler = Callable[[Event], Awaitable[None]]


class EventEngine:
    """A very small synchronous pub/sub loop with optional async handlers."""

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._async_handlers: dict[str, list[AsyncHandler]] = defaultdict(list)
        self._generic: list[Handler] = []

    def register(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def register_async(self, event_type: str, handler: AsyncHandler) -> None:
        self._async_handlers[event_type].append(handler)

    def register_generic(self, handler: Handler) -> None:
        self._generic.append(handler)

    def unregister(self, event_type: str, handler: Handler) -> None:
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    def put(self, event: Event) -> None:
        for h in self._handlers.get(event.type, []):
            try:
                h(event)
            except Exception:
                logger.exception("Handler for %s raised", event.type)
        for h in self._generic:
            try:
                h(event)
            except Exception:
                logger.exception("Generic handler raised on %s", event.type)

    async def put_async(self, event: Event) -> None:
        self.put(event)
        tasks = [h(event) for h in self._async_handlers.get(event.type, [])]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
