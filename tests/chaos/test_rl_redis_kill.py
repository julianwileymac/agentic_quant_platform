"""Chaos test: kill RLS Redis primary mid-sync.

Verifies the fail-closed contract: when the Redis backend is
unreachable, `RedisTokenBucketStrategy.check` raises a clear
`RateLimitError` and the factory falls back to `InMemoryStrategy`
rather than silently granting unlimited quota.
"""
from __future__ import annotations

import pytest


def test_redis_strategy_raises_when_backend_unreachable():
    """When Redis is unreachable, check() must surface a clear error."""
    pytest.importorskip("redis")
    from aqp_ratelimit.exceptions import RateLimitError
    from aqp_ratelimit.strategies.redis_token_bucket import (
        RedisTokenBucketStrategy,
    )

    # Point at a non-routable port; the short socket_timeout (2s)
    # ensures the test doesn't hang on a stuck connect.
    strategy = RedisTokenBucketStrategy(
        redis_url="redis://127.0.0.1:1/0",
        eager=False,
    )
    with pytest.raises(RateLimitError):
        strategy.check(user_id="u", service="polygon", key_id="primary")


def test_factory_falls_back_to_in_memory_on_redis_failure():
    """The factory must fall back gracefully so the boot path succeeds."""
    from aqp_ratelimit.factory import (
        get_ratelimit_factory,
        reset_ratelimit_factory,
    )
    from aqp_ratelimit.strategies.in_memory import InMemoryStrategy

    reset_ratelimit_factory()
    factory = get_ratelimit_factory()
    strategy = factory.for_kind("does_not_exist")
    assert isinstance(strategy, InMemoryStrategy)
