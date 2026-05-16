"""Tests for the Phase 5 L1 LRU + single-flight layer."""
from __future__ import annotations

import time

import pytest

from aqp.cache.client import MetadataCache, _L1Cache, reset_cache_singleton
from aqp.cache.keys import by_id_hash, names_zset
from aqp.config import settings


@pytest.fixture(autouse=True)
def force_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_enabled", True)
    monkeypatch.setattr(settings, "cache_redis_url", "redis://nonexistent.local:9999/0")
    monkeypatch.setattr(settings, "cache_l1_enabled", True)
    monkeypatch.setattr(settings, "cache_l1_ttl_s", 5)
    monkeypatch.setattr(settings, "cache_l1_max_entries", 8)
    reset_cache_singleton()
    yield
    reset_cache_singleton()


def test_l1_serves_repeat_hgetall_without_l2_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MetadataCache(url="redis://nonexistent.local:9999/0")
    key = by_id_hash("datasets", "abc")
    cache.hset(key, {"id": "abc", "name": "demo"})
    first = cache.hgetall(key)
    # Patch the in-memory backend's hgetall to a sentinel; if L1 works
    # the second call should not hit it.
    fail = {"called": False}

    def _explode(_):
        fail["called"] = True
        raise AssertionError("L1 should have served this call")

    cache._memory.hgetall = _explode  # type: ignore[attr-defined]
    second = cache.hgetall(key)
    assert first == second
    assert fail["called"] is False


def test_l1_invalidates_on_hset(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = MetadataCache(url="redis://nonexistent.local:9999/0")
    key = by_id_hash("datasets", "abc")
    cache.hset(key, {"id": "abc", "name": "demo"})
    _ = cache.hgetall(key)  # primes L1
    cache.hset(key, {"id": "abc", "name": "updated"})
    payload = cache.hgetall(key)
    assert payload["name"] == "updated"


def test_l1_invalidates_on_zadd_and_zrem() -> None:
    cache = MetadataCache(url="redis://nonexistent.local:9999/0")
    key = names_zset("datasets")
    cache.zadd(key, {"foo": 0.0})
    page1 = cache.zrange_lex(key, prefix="", offset=0, count=10)
    cache.zadd(key, {"bar": 0.0})
    page2 = cache.zrange_lex(key, prefix="", offset=0, count=10)
    assert sorted(page2) == ["bar", "foo"]
    assert page1 == ["foo"]


def test_l1_eviction_respects_max_entries() -> None:
    # ``_L1Cache`` floors max_entries at 64 so production deploys can't
    # accidentally configure a tiny cache. The eviction logic is what
    # we're testing — fill above the floor and verify the oldest get
    # evicted.
    l1 = _L1Cache(max_entries=64, ttl_seconds=60)
    for i in range(80):
        l1.set(f"k{i}", i)
    # Oldest 16 entries evicted; last 64 remain.
    for i in range(16):
        hit, _ = l1.get(f"k{i}")
        assert hit is False
    for i in range(16, 80):
        hit, val = l1.get(f"k{i}")
        assert hit is True and val == i


def test_l1_respects_ttl() -> None:
    l1 = _L1Cache(max_entries=10, ttl_seconds=1)
    l1.set("k1", 42)
    hit, val = l1.get("k1")
    assert hit is True and val == 42
    time.sleep(1.1)
    hit2, _ = l1.get("k1")
    assert hit2 is False


def test_l1_disabled_when_setting_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_l1_enabled", False)
    reset_cache_singleton()
    cache = MetadataCache(url="redis://nonexistent.local:9999/0")
    assert cache._l1 is None
