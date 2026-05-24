"""Content-addressable replay cache for backtest reproducibility.

The cache is intentionally optional: production live trading and
intraday research call the live vendor APIs through the inline
proxy + RLS chain. Only ``aqp context use local`` / ``dev`` /
branch-deployment profiles toggle ``AQP_RATELIMIT_REPLAY_MODE=replay``,
at which point cache misses raise and a backtest must explicitly
record a new cassette before re-running.
"""
from __future__ import annotations

from aqp_ratelimit.replay_cache.policies import (
    DEFAULT_TTL_POLICIES,
    CachePolicy,
    pick_policy_for_url,
)
from aqp_ratelimit.replay_cache.store import (
    InMemoryCassetteStore,
    S3CassetteStore,
    hash_request,
)

__all__ = [
    "CachePolicy",
    "DEFAULT_TTL_POLICIES",
    "InMemoryCassetteStore",
    "S3CassetteStore",
    "hash_request",
    "pick_policy_for_url",
]
