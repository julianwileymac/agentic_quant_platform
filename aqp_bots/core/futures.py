"""Order request/response :class:`asyncio.Future` registry.

When a strategy submits an order it returns immediately with a
:class:`asyncio.Future` keyed by ``client_order_id``. The execution
adapter resolves the future when the venue replies with an ack /
reject / fill. This is the "request-response parity in an async
world" pattern from blueprint §I.3.

The registry also holds an LRU cache for content-hash dedup so we can
detect a retry of the exact same logical order and return the original
future instead of re-submitting (blueprint §G.4).
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


class OrderFutureRegistry:
    """Track in-flight orders by ``client_order_id``.

    Two layers:

    - ``futures`` — live :class:`asyncio.Future` objects keyed by
      ``client_order_id``. Cleared when the order reaches a terminal
      state (filled / cancelled / rejected / expired).
    - ``content_hash_lru`` — bounded LRU mapping ``content_hash`` →
      ``client_order_id`` so a retry of the same logical order returns
      the original future. Defaults to 4096 entries (knob on
      :class:`ExecutionLayerSpec.idempotency_lru_size`).
    """

    def __init__(self, *, lru_size: int = 4096) -> None:
        self._lru_size = lru_size
        self._futures: dict[str, asyncio.Future[Any]] = {}
        self._content_lru: OrderedDict[str, str] = OrderedDict()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Submission path
    # ------------------------------------------------------------------

    async def submit(
        self,
        client_order_id: str,
        *,
        content_hash: str | None = None,
    ) -> tuple[asyncio.Future[Any], bool]:
        """Register a new in-flight order.

        Returns ``(future, is_new)``. When ``content_hash`` matches an
        existing in-flight order ``is_new=False`` and the *original*
        future is returned (idempotent retry).
        """
        async with self._lock:
            if content_hash:
                existing_id = self._content_lru.get(content_hash)
                if existing_id and existing_id in self._futures:
                    self._content_lru.move_to_end(content_hash)
                    return self._futures[existing_id], False

            fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
            self._futures[client_order_id] = fut

            if content_hash:
                self._content_lru[content_hash] = client_order_id
                self._content_lru.move_to_end(content_hash)
                while len(self._content_lru) > self._lru_size:
                    self._content_lru.popitem(last=False)
            return fut, True

    # ------------------------------------------------------------------
    # Resolution path
    # ------------------------------------------------------------------

    def resolve(self, client_order_id: str, result: Any) -> bool:
        """Resolve the future with ``result``. Returns True if found."""
        fut = self._futures.pop(client_order_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(result)
        return True

    def reject(self, client_order_id: str, exc: BaseException) -> bool:
        """Reject the future with ``exc``. Returns True if found."""
        fut = self._futures.pop(client_order_id, None)
        if fut is None or fut.done():
            return False
        fut.set_exception(exc)
        return True

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def in_flight(self) -> tuple[str, ...]:
        """Return the client_order_ids currently in flight."""
        return tuple(self._futures.keys())

    def __len__(self) -> int:
        return len(self._futures)


__all__ = ["OrderFutureRegistry"]
