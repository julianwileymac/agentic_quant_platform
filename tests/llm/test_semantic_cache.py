"""Tests for the Phase 5 semantic LLM completion cache.

We monkeypatch the embedding helper + Redis client so the tests run
hermetically; the production wire-up uses RedisVL + the platform
embeddings provider.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aqp.config import settings
from aqp.llm.cache.semantic import (
    CachedCompletion,
    SemanticLLMCache,
    reset_semantic_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_semantic_cache_for_tests()
    yield
    reset_semantic_cache_for_tests()


def _build_cache(monkeypatch: pytest.MonkeyPatch) -> tuple[SemanticLLMCache, dict[str, Any]]:
    """Build a SemanticLLMCache wired to a fake Redis + embedding stub."""
    store: dict[str, Any] = {"strings": {}, "sets": {}}

    class _FakeRedis:
        def set(self, key, value, ex=None):
            store["strings"][key] = value

        def get(self, key):
            return store["strings"].get(key)

        def sadd(self, key, *members):
            bucket = store["sets"].setdefault(key, set())
            for m in members:
                bucket.add(str(m))
            return len(members)

        def srem(self, key, *members):
            bucket = store["sets"].get(key, set())
            for m in members:
                bucket.discard(str(m))
            return len(members)

        def smembers(self, key):
            return set(store["sets"].get(key, set()))

        def scard(self, key):
            return len(store["sets"].get(key, set()))

        def srandmember(self, key, n):
            return list(store["sets"].get(key, set()))[:n]

        def delete(self, key):
            store["strings"].pop(key, None)

    cache = SemanticLLMCache(threshold=0.9, ttl_seconds=60, max_entries=10)
    cache._client = _FakeRedis()  # type: ignore[assignment]
    monkeypatch.setattr(settings, "llm_semantic_cache_enabled", True)

    def _embed(text: str) -> list[float]:
        # Deterministic but discriminating: hash the full text into 16
        # buckets so different prompts produce visibly different vectors.
        # Same prompt always returns the same vector (similarity=1.0);
        # different prompts produce cosine similarity << 1.
        import hashlib

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [float(b) for b in digest[:16]]

    monkeypatch.setattr("aqp.llm.cache.semantic._embed_text", _embed)
    return cache, store


def test_store_then_lookup_returns_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    cache, _ = _build_cache(monkeypatch)
    messages = [{"role": "user", "content": "What is the rolling Sharpe?"}]
    response = {
        "choices": [{"message": {"role": "assistant", "content": "Sharpe rolling..."}}],
        "model": "gpt-test",
    }
    cache.store(messages, "gpt-test", response)

    hit = cache.lookup(messages, "gpt-test")
    assert isinstance(hit, CachedCompletion)
    assert hit.content == "Sharpe rolling..."
    assert hit.similarity >= 0.9


def test_lookup_miss_when_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    cache, _ = _build_cache(monkeypatch)
    cache.store(
        [{"role": "user", "content": "Compute the Sharpe ratio"}],
        "gpt-test",
        {
            "choices": [
                {"message": {"role": "assistant", "content": "Sharpe = mean / std"}}
            ],
            "model": "gpt-test",
        },
    )
    # Very different prompt → ord-based embedding diverges.
    miss = cache.lookup(
        [{"role": "user", "content": "Explain the kelly criterion"}],
        "gpt-test",
    )
    assert miss is None


def test_disabled_when_setting_off(monkeypatch: pytest.MonkeyPatch) -> None:
    cache, _ = _build_cache(monkeypatch)
    monkeypatch.setattr(settings, "llm_semantic_cache_enabled", False)
    assert cache.enabled is False
    out = cache.lookup([{"role": "user", "content": "hi"}], "gpt-test")
    assert out is None


def test_disabled_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    cache, _ = _build_cache(monkeypatch)
    cache._client = None
    assert cache.enabled is False


def test_model_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    cache, _ = _build_cache(monkeypatch)
    cache.store(
        [{"role": "user", "content": "ping"}],
        "gpt-a",
        {"choices": [{"message": {"role": "assistant", "content": "pong-a"}}], "model": "gpt-a"},
    )
    assert cache.lookup([{"role": "user", "content": "ping"}], "gpt-b") is None
    assert (
        cache.lookup([{"role": "user", "content": "ping"}], "gpt-a").content
        == "pong-a"
    )
