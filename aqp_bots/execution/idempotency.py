"""Idempotency cache for outbound orders.

Blueprint §G.4: every outbound order carries a UUIDv7 ``client_order_id``
+ a content hash. The adapter (or this cache) maintains a deduplication
LRU; if a retry arrives with the same ``client_order_id`` the cached
result is returned instead of re-submitting.

This is also the place where the kernel's
:class:`aqp_bots.core.futures.OrderFutureRegistry` consults the
content-hash LRU to detect a retry of the same logical order before
allocating a fresh :class:`asyncio.Future`.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any

from aqp_bots.schemas.trading import NewOrder


def order_content_hash(order: NewOrder) -> str:
    """Stable content hash for idempotency dedup.

    Hashes the immutable fields of a :class:`NewOrder` — venue, symbol,
    side, qty, type, price, time-in-force — so a retry of the same
    logical order (e.g. after a transport error) is recognized as a
    duplicate regardless of the random UUIDv7 in ``client_order_id``.
    """
    payload = "|".join(
        [
            order.venue,
            order.symbol,
            str(order.side.value if hasattr(order.side, "value") else order.side),
            str(order.quantity),
            order.order_type,
            str(order.time_in_force.value)
            if hasattr(order.time_in_force, "value")
            else str(order.time_in_force),
            str(order.limit_price or ""),
            str(order.stop_price or ""),
            str(order.parent_order_id),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class IdempotencyCache:
    """LRU mapping ``content_hash -> client_order_id``.

    Bounded by ``size`` entries (default 4096; configurable per-bot
    via :attr:`ExecutionLayerSpec.idempotency_lru_size`).
    """

    def __init__(self, *, size: int = 4096) -> None:
        self._size = size
        self._map: OrderedDict[str, str] = OrderedDict()

    def get(self, content_hash: str) -> str | None:
        """Return the cached ``client_order_id`` for ``content_hash`` (or None)."""
        client_order_id = self._map.get(content_hash)
        if client_order_id is not None:
            self._map.move_to_end(content_hash)
        return client_order_id

    def put(self, content_hash: str, client_order_id: str) -> None:
        self._map[content_hash] = client_order_id
        self._map.move_to_end(content_hash)
        while len(self._map) > self._size:
            self._map.popitem(last=False)

    def __len__(self) -> int:
        return len(self._map)

    def clear(self) -> None:
        self._map.clear()

    def is_duplicate(self, order: NewOrder) -> str | None:
        """Convenience: hash + lookup in one call."""
        return self.get(order_content_hash(order))


__all__ = ["IdempotencyCache", "order_content_hash"]
