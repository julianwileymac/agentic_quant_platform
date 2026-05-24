"""Factory + metaclass registration tests."""
from __future__ import annotations

from aqp_ratelimit.factory import get_ratelimit_factory, reset_ratelimit_factory
from aqp_ratelimit.strategies.base import (
    IngestionRateLimitStrategy,
    list_ratelimit_strategy_classes,
)


def test_metaclass_registers_built_in_strategies():
    classes = list_ratelimit_strategy_classes()
    # The two strategies always shipped (in-memory + redis token bucket)
    # must be visible regardless of optional deps.
    aliases = list(classes.keys())
    assert "InMemoryStrategy" in aliases
    assert "RedisTokenBucketStrategy" in aliases


def test_metaclass_skips_abstract_base():
    classes = list_ratelimit_strategy_classes()
    assert IngestionRateLimitStrategy.__name__ not in classes


def test_factory_returns_singleton_per_kind():
    reset_ratelimit_factory()
    f1 = get_ratelimit_factory()
    f2 = get_ratelimit_factory()
    assert f1 is f2


def test_factory_falls_back_to_in_memory_when_redis_unavailable(monkeypatch):
    reset_ratelimit_factory()

    # Force the resolver to look for an unregistered kind; should
    # fall back to in-memory rather than crash.
    factory = get_ratelimit_factory()
    strategy = factory.for_kind("does_not_exist")
    assert strategy.__class__.__name__ == "InMemoryStrategy"


def test_factory_default_resolves_to_concrete_strategy():
    reset_ratelimit_factory()
    factory = get_ratelimit_factory()
    strategy = factory.default()
    assert isinstance(strategy, IngestionRateLimitStrategy)
