"""Replay-cache + cassette policy tests."""
from __future__ import annotations

import pytest

from aqp_ratelimit.exceptions import RateLimitExceeded
from aqp_ratelimit.replay_cache import (
    InMemoryCassetteStore,
    hash_request,
    pick_policy_for_url,
)
from aqp_ratelimit.replay_cache.store import CassetteEntry
from aqp_ratelimit.strategies.in_memory import InMemoryStrategy
from aqp_ratelimit.strategies.replay_cache import ReplayCacheStrategy, ReplayMode


def test_hash_request_is_stable():
    a = hash_request(method="GET", url="https://api.polygon.io/v2/aggs/ticker/AAPL")
    b = hash_request(method="GET", url="https://api.polygon.io/v2/aggs/ticker/AAPL")
    assert a == b


def test_hash_request_differs_per_url():
    a = hash_request(method="GET", url="https://api.polygon.io/v2/aggs/ticker/AAPL")
    b = hash_request(method="GET", url="https://api.polygon.io/v2/aggs/ticker/MSFT")
    assert a != b


def test_pick_policy_for_historical_url():
    policy = pick_policy_for_url(
        "/v2/aggs/ticker/AAPL/range/1/minute/2020-01-01/2020-01-02"
    )
    assert policy.name == "historical"
    assert policy.ttl_seconds is None


def test_pick_policy_defaults_to_realtime():
    policy = pick_policy_for_url("/snapshot/latest")
    assert policy.name == "realtime"


def test_replay_mode_off_delegates_to_inner():
    inner = InMemoryStrategy(capacity=10, refill_rate=0.0)
    wrapper = ReplayCacheStrategy(inner=inner, mode=ReplayMode.OFF)
    decision = wrapper.check(user_id="u1", service="polygon", key_id="primary")
    assert decision.allow is True


def test_replay_mode_replay_serves_from_cache():
    cache = InMemoryCassetteStore()
    req_hash = "abc123"
    cache.put(
        CassetteEntry(
            request_hash=req_hash,
            method="GET",
            url="https://api.polygon.io/v2/aggs/...",
            status=200,
            headers={},
            body=b'{"results":[]}',
        )
    )
    wrapper = ReplayCacheStrategy(
        inner=InMemoryStrategy(),
        mode=ReplayMode.REPLAY,
        cache_index=cache,
    )
    decision = wrapper.check(
        user_id="u1",
        service="polygon",
        key_id="primary",
        ctx={"request_hash": req_hash},
    )
    assert decision.allow is True
    assert decision.metadata.get("decision") == "cached"


def test_replay_mode_replay_raises_on_cache_miss():
    cache = InMemoryCassetteStore()
    wrapper = ReplayCacheStrategy(
        inner=InMemoryStrategy(),
        mode=ReplayMode.REPLAY,
        cache_index=cache,
    )
    with pytest.raises(RateLimitExceeded):
        wrapper.check(
            user_id="u1",
            service="polygon",
            key_id="primary",
            ctx={"request_hash": "no-such-hash"},
        )
