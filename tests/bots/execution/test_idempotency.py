"""Phase 4: Idempotency cache (UUIDv7 + content hash LRU)."""
from __future__ import annotations

from decimal import Decimal

from aqp_bots.execution.idempotency import IdempotencyCache, order_content_hash
from aqp_bots.schemas.trading import NewOrder, Side, TimeInForce


def _order(client_order_id: str = "coid-1") -> NewOrder:
    return NewOrder(
        venue="binance",
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=Decimal("0.5"),
        order_type="limit",
        time_in_force=TimeInForce.GTC,
        limit_price=Decimal("65000"),
        client_order_id=client_order_id,
    )


def test_content_hash_stable_for_same_order() -> None:
    a = _order("coid-1")
    b = _order("coid-2")  # same content, different coid
    assert order_content_hash(a) == order_content_hash(b)


def test_content_hash_changes_when_qty_changes() -> None:
    a = _order()
    b = NewOrder(
        venue=a.venue,
        symbol=a.symbol,
        side=a.side,
        quantity=Decimal("1"),
        order_type=a.order_type,
        time_in_force=a.time_in_force,
        limit_price=a.limit_price,
        client_order_id="coid-9",
    )
    assert order_content_hash(a) != order_content_hash(b)


def test_lru_dedup() -> None:
    cache = IdempotencyCache(size=2)
    h1 = order_content_hash(_order("coid-1"))
    cache.put(h1, "coid-1")
    assert cache.get(h1) == "coid-1"
    # Add another distinct entry.
    cache.put("h2", "coid-2")
    cache.put("h3", "coid-3")
    # h1 should have been evicted (LRU, size=2).
    assert cache.get(h1) is None


def test_is_duplicate_helper() -> None:
    cache = IdempotencyCache()
    o = _order("coid-1")
    assert cache.is_duplicate(o) is None
    cache.put(order_content_hash(o), o.client_order_id)
    assert cache.is_duplicate(o) == "coid-1"
