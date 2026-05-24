"""Message bus protocol + default asyncio-queue implementation.

The kernel's single-thread asyncio runtime dispatches every event
through the bus. Default backend is :class:`AsyncQueueBus` (bounded
:class:`asyncio.Queue` with explicit backpressure); HFT bots swap in
the lock-free SPSC ring buffer from :mod:`aqp_bots.hft.ring_buffer`
(Phase 7) without changing any consumer code.

Design choices (blueprint §I.2):

- Bounded queues — unbounded queues hide pipeline stalls until OOM.
- Per-topic dispatch — strategies subscribe to topics ("ticks/AAPL",
  "fills/binance") rather than the whole firehose.
- Drop-on-full policy is opt-in per topic — by default a full queue
  blocks the producer (deterministic, but slow).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class BusFullError(RuntimeError):
    """Raised when a bus queue is full and the producer's drop policy is reject."""


@runtime_checkable
class MessageBus(Protocol):
    """Pluggable in-bot message bus.

    Conforming implementations:

    - :class:`AsyncQueueBus` — default, asyncio.Queue based
    - ``RingBufferBus`` — HFT, Cython SPSC ring buffer (Phase 7)
    """

    async def publish(self, topic: str, message: Any) -> None:
        ...

    async def subscribe(self, topic: str) -> AsyncIterator[Any]:
        ...

    async def aclose(self) -> None:
        ...

    def queue_depth(self, topic: str) -> int:
        ...


class AsyncQueueBus:
    """Default in-bot bus backed by per-topic :class:`asyncio.Queue`."""

    def __init__(self, *, default_maxsize: int = 4096) -> None:
        self._default_maxsize = default_maxsize
        self._queues: dict[str, asyncio.Queue[Any]] = {}
        self._closed: bool = False

    def _get_queue(self, topic: str) -> asyncio.Queue[Any]:
        q = self._queues.get(topic)
        if q is None:
            q = asyncio.Queue(maxsize=self._default_maxsize)
            self._queues[topic] = q
        return q

    async def publish(self, topic: str, message: Any) -> None:
        if self._closed:
            return
        q = self._get_queue(topic)
        await q.put(message)

    def publish_nowait(self, topic: str, message: Any, *, drop_on_full: bool = False) -> bool:
        """Publish without await.

        Returns True on success.  When the queue is full:
        - ``drop_on_full=True`` drops the message and returns False
        - ``drop_on_full=False`` (default) raises :class:`BusFullError`
        """
        if self._closed:
            return False
        q = self._get_queue(topic)
        try:
            q.put_nowait(message)
            return True
        except asyncio.QueueFull:
            if drop_on_full:
                logger.warning("bus dropped message on full queue topic=%s", topic)
                return False
            raise BusFullError(f"bus topic {topic!r} full ({q.qsize()}/{q.maxsize})")

    async def subscribe(self, topic: str) -> AsyncIterator[Any]:
        """Yield messages on ``topic`` until the bus is closed."""
        q = self._get_queue(topic)
        while not self._closed:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if self._closed:
                    return
                continue
            yield msg

    def queue_depth(self, topic: str) -> int:
        q = self._queues.get(topic)
        return q.qsize() if q else 0

    async def aclose(self) -> None:
        """Drain + close every queue."""
        self._closed = True
        # Allow consumers to drain the timeout window in subscribe().
        await asyncio.sleep(0)


__all__ = [
    "AsyncQueueBus",
    "BusFullError",
    "MessageBus",
]
