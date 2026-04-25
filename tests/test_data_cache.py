"""Tests for the Redis-backed JSON cache (``aqp.data.cache``).

We avoid a real Redis dependency by monkey-patching the module's
client factories with a tiny in-memory fake that implements the subset
of the Redis API we use (``get``, ``setex``, ``delete``, ``scan``).
"""
from __future__ import annotations

import time
from typing import Any

import pytest

from aqp.data import cache as cache_mod


# --------------------------------------------------------------------------
# In-memory fake Redis (sync + async dual role)
# --------------------------------------------------------------------------


class _FakeRedis:
    """Minimal subset of redis-py sufficient for our cache helper."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}

    def _expired(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        _, expires_at = entry
        if expires_at < time.time():
            self._store.pop(key, None)
            return True
        return False

    def get(self, key: str) -> str | None:  # pragma: no cover - sync path
        if self._expired(key):
            return None
        return self._store[key][0]

    def setex(self, key: str, ttl: int, value: str) -> bool:  # pragma: no cover
        self._store[key] = (value, time.time() + ttl)
        return True

    def delete(self, *keys: str) -> int:  # pragma: no cover
        count = 0
        for key in keys:
            if key in self._store:
                self._store.pop(key)
                count += 1
        return count

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):  # pragma: no cover
        keys = [k for k in self._store if match is None or _fnmatch(k, match)]
        return 0, keys


class _AsyncFakeRedis(_FakeRedis):
    """Async variant with awaitable methods."""

    async def get(self, key: str) -> str | None:  # type: ignore[override]
        return super().get(key)

    async def setex(self, key: str, ttl: int, value: str) -> bool:  # type: ignore[override]
        return super().setex(key, ttl, value)

    async def delete(self, *keys: str) -> int:  # type: ignore[override]
        return super().delete(*keys)

    async def close(self) -> None:
        return None


def _fnmatch(key: str, pattern: str) -> bool:
    import fnmatch

    return fnmatch.fnmatch(key, pattern)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    """Install a single fake redis shared between the sync + async factories."""
    store = _FakeRedis()
    async_store = _AsyncFakeRedis()
    # Share the same underlying dict so sync/async see the same data.
    async_store._store = store._store

    monkeypatch.setattr(cache_mod, "_sync_client", lambda: store)
    monkeypatch.setattr(cache_mod, "_async_client", lambda: async_store)
    return store


@pytest.fixture
def redis_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_mod, "_sync_client", lambda: None)
    monkeypatch.setattr(cache_mod, "_async_client", lambda: None)


# --------------------------------------------------------------------------
# Sync helpers
# --------------------------------------------------------------------------


def test_cached_json_sync_hits_after_first_call(fake_redis: _FakeRedis) -> None:
    calls = {"n": 0}

    def producer() -> dict[str, Any]:
        calls["n"] += 1
        return {"value": 42}

    out = cache_mod.cached_json_sync("security", "AAPL", 60, producer)
    assert out == {"value": 42}
    assert calls["n"] == 1

    again = cache_mod.cached_json_sync("security", "AAPL", 60, producer)
    assert again == {"value": 42}
    assert calls["n"] == 1


def test_cache_set_and_get_roundtrip(fake_redis: _FakeRedis) -> None:
    ok = cache_mod.cache_set("security", "MSFT", {"pe": 30.5}, ttl=120)
    assert ok
    assert cache_mod.cache_get("security", "MSFT") == {"pe": 30.5}


def test_invalidate_scope_removes_all_keys(fake_redis: _FakeRedis) -> None:
    cache_mod.cache_set("security", "AAPL", {"a": 1}, 60)
    cache_mod.cache_set("security", "MSFT", {"a": 2}, 60)
    cache_mod.cache_set("quote", "AAPL", {"p": 100}, 60)

    removed = cache_mod.cache_invalidate("security")
    assert removed >= 2
    assert cache_mod.cache_get("security", "AAPL") is None
    assert cache_mod.cache_get("quote", "AAPL") == {"p": 100}


def test_graceful_degrade_when_redis_down(redis_down: None) -> None:
    # Producer must still run and value must still be returned.
    calls = {"n": 0}

    def producer() -> dict[str, Any]:
        calls["n"] += 1
        return {"ok": True}

    first = cache_mod.cached_json_sync("security", "AAPL", 60, producer)
    second = cache_mod.cached_json_sync("security", "AAPL", 60, producer)
    assert first == second == {"ok": True}
    # Without Redis, every call re-invokes the producer.
    assert calls["n"] == 2


def test_stale_on_error_falls_back_to_cached(fake_redis: _FakeRedis) -> None:
    def good() -> dict[str, Any]:
        return {"value": 1}

    def bad() -> dict[str, Any]:
        raise RuntimeError("boom")

    cache_mod.cached_json_sync("security", "AAPL", ttl=1, producer=good)

    # Wait for the primary key to expire but the stale copy to remain.
    time.sleep(1.1)

    out = cache_mod.cached_json_sync("security", "AAPL", ttl=1, producer=bad)
    assert out == {"value": 1}


def test_circular_payload_is_not_cached(fake_redis: _FakeRedis) -> None:
    """Circular references cannot be serialized even with ``default=str``."""
    payload: dict[str, Any] = {"self": None}
    payload["self"] = payload

    ok = cache_mod.cache_set("security", "BADKEY", payload, ttl=60)
    assert ok is False
    assert cache_mod.cache_get("security", "BADKEY") is None


# --------------------------------------------------------------------------
# Async path
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cached_json_async_hit(fake_redis: _FakeRedis) -> None:
    calls = {"n": 0}

    async def producer() -> dict[str, Any]:
        calls["n"] += 1
        return {"value": "async"}

    first = await cache_mod.cached_json("security", "AAPL", 60, producer)
    second = await cache_mod.cached_json("security", "AAPL", 60, producer)
    assert first == second == {"value": "async"}
    assert calls["n"] == 1


@pytest.mark.anyio
async def test_cached_json_async_accepts_sync_callable(fake_redis: _FakeRedis) -> None:
    def producer() -> dict[str, Any]:
        return {"sync": True}

    result = await cache_mod.cached_json("security", "GOOG", 60, producer)
    assert result == {"sync": True}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
