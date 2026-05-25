"""Smoke tests for :class:`aqp_models.handlers.CacheHandler`."""
from __future__ import annotations

from aqp_models.handlers import CacheHandler


def test_warm_returns_loaded_entry() -> None:
    cache = CacheHandler(max_entries=4, max_vram_bytes=10_000)
    entry = cache.warm(key="lgb-1d", loader=lambda: object())
    assert entry.key == "lgb-1d"
    assert entry.hits == 0


def test_lookup_increments_hits() -> None:
    cache = CacheHandler(max_entries=4, max_vram_bytes=10_000)
    cache.warm(key="m", loader=lambda: object())
    entry = cache.lookup("m")
    assert entry is not None
    assert entry.hits == 1
    again = cache.lookup("m")
    assert again is not None
    assert again.hits == 2


def test_max_entries_evicts_lru() -> None:
    cache = CacheHandler(max_entries=2, max_vram_bytes=10_000)
    cache.warm(key="a", loader=lambda: object())
    cache.warm(key="b", loader=lambda: object())
    cache.warm(key="c", loader=lambda: object())
    assert cache.lookup("a") is None
    assert cache.lookup("b") is not None
    assert cache.lookup("c") is not None


def test_stats_descriptor() -> None:
    cache = CacheHandler(max_entries=4, max_vram_bytes=10_000)
    cache.warm(key="x", loader=lambda: object())
    stats = cache.stats()
    assert stats["n_entries"] == 1
    assert any(entry["key"] == "x" for entry in stats["entries"])


def test_invoke_dispatches_op() -> None:
    cache = CacheHandler(max_entries=4, max_vram_bytes=10_000)
    result = cache.invoke(op="stats")
    assert result.ok is True
    assert "max_entries" in result.data
