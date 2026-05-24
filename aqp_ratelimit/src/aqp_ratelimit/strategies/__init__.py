"""Concrete rate-limit strategies.

Importing this package triggers eager metaclass registration of every
shipped strategy so :func:`aqp_ratelimit.strategies.base.list_ratelimit_strategy_classes`
returns the full enumeration without a filesystem scan.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp_ratelimit.strategies.in_memory import InMemoryStrategy
from aqp_ratelimit.strategies.redis_token_bucket import RedisTokenBucketStrategy

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_ratelimit.strategies.per_agent import PerAgentStrategy  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_ratelimit.strategies.replay_cache import ReplayCacheStrategy  # noqa: F401

__all__ = [
    "InMemoryStrategy",
    "RedisTokenBucketStrategy",
]
