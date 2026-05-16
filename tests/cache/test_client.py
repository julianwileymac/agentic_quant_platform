"""Tests for the in-memory fallback of :class:`MetadataCache`."""
from __future__ import annotations

import pytest

from aqp.cache.client import MetadataCache, get_cache, reset_cache_singleton
from aqp.cache.keys import by_id_hash, names_zset
from aqp.cache.invalidation import cache_invalidate, cache_write_through
from aqp.config import settings


@pytest.fixture(autouse=True)
def force_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the in-memory backend so the suite never touches a real Redis."""
    monkeypatch.setattr(settings, "cache_enabled", True)
    monkeypatch.setattr(settings, "cache_redis_url", "redis://nonexistent.local:9999/0")
    reset_cache_singleton()
    yield
    reset_cache_singleton()


def _fresh_cache() -> MetadataCache:
    return MetadataCache(url="redis://nonexistent.local:9999/0")


def test_cache_falls_back_to_memory_when_redis_unreachable() -> None:
    cache = _fresh_cache()
    assert cache.is_remote is False


def test_zadd_zrange_lex_round_trip() -> None:
    cache = _fresh_cache()
    key = names_zset("dataset_kinds")
    cache.zadd(key, {"alpha": 0.0, "beta": 0.0, "gamma": 0.0})
    assert cache.zcard(key) == 3
    page = cache.zrange_lex(key, prefix="b", offset=0, count=10)
    assert page == ["beta"]
    assert cache.zrange_lex(key, prefix="", offset=0, count=2) == ["alpha", "beta"]


def test_hash_round_trip() -> None:
    cache = _fresh_cache()
    key = by_id_hash("datasets", "abc-123")
    cache.hset(key, {"id": "abc-123", "name": "demo", "tags": ["alpha", "beta"]})
    payload = cache.hgetall(key)
    assert payload["id"] == "abc-123"
    assert payload["name"] == "demo"
    # Lists / dicts round-trip via JSON encode/decode.
    assert payload["tags"] == ["alpha", "beta"]


def test_write_through_and_invalidate_cycle() -> None:
    cache_write_through(
        "datasets",
        {"id": "t1", "name": "trades_eod", "iceberg_identifier": "aqp_silver_demo.trades"},
    )
    cache_write_through(
        "datasets",
        {"id": "t2", "name": "trades_intraday", "iceberg_identifier": "aqp_silver_demo.intra"},
    )
    # ``cache_write_through`` writes through :func:`get_cache` (the
    # process-wide singleton). Reading from a separate ``MetadataCache``
    # instance would land on a different in-memory backend, so the
    # assertion must use the same singleton.
    cache = get_cache()
    page = cache.zrange_lex(names_zset("datasets"), prefix="trades", offset=0, count=10)
    assert sorted(page) == ["trades_eod", "trades_intraday"]
    cache_invalidate("datasets", "t1", name="trades_eod")
    page = cache.zrange_lex(names_zset("datasets"), prefix="trades", offset=0, count=10)
    assert page == ["trades_intraday"]


def test_unknown_category_in_write_through_is_silent() -> None:
    # Should NOT raise — we log a warning and skip so a typo can't take
    # down a mutation route.
    cache_write_through("not_a_real_category", {"id": "x", "name": "x"})  # type: ignore[arg-type]
