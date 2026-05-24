"""Lua script tests using fakeredis.

These tests pin the Redis-side bucket math contract. The Lua source
is loaded from disk so the same script the Go server + Python
strategy use is exercised here.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

fakeredis = pytest.importorskip("fakeredis")


LUA_DIR = Path(__file__).resolve().parents[1] / "lua"


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def token_bucket_script(redis_client):
    source = (LUA_DIR / "token_bucket.lua").read_text(encoding="utf-8")
    return redis_client.register_script(source)


def test_token_bucket_allows_under_capacity(redis_client, token_bucket_script):
    key = "aqp:rl:u1:polygon:primary"
    now_ms = int(time.time() * 1000)
    result = token_bucket_script(
        keys=[key],
        args=[10, 1.0, 1.0, now_ms, 3],
    )
    assert int(result[0]) == 1
    assert float(result[1]) == pytest.approx(7)
    assert int(result[2]) == 0


def test_token_bucket_denies_over_capacity(redis_client, token_bucket_script):
    key = "aqp:rl:u1:polygon:primary"
    now_ms = int(time.time() * 1000)
    for _ in range(5):
        token_bucket_script(keys=[key], args=[5, 0.0, 1.0, now_ms, 1])
    result = token_bucket_script(keys=[key], args=[5, 0.0, 1.0, now_ms, 1])
    assert int(result[0]) == 0
    assert float(result[1]) == pytest.approx(0)


def test_token_bucket_isolates_users(redis_client, token_bucket_script):
    now_ms = int(time.time() * 1000)
    a = token_bucket_script(
        keys=["aqp:rl:alice:polygon:primary"],
        args=[1, 0.0, 1.0, now_ms, 1],
    )
    b = token_bucket_script(
        keys=["aqp:rl:bob:polygon:primary"],
        args=[1, 0.0, 1.0, now_ms, 1],
    )
    assert int(a[0]) == 1
    assert int(b[0]) == 1


def test_token_bucket_refills_with_elapsed_time(redis_client, token_bucket_script):
    key = "aqp:rl:u1:polygon:primary"
    now_ms = int(time.time() * 1000)
    # Drain.
    for _ in range(5):
        token_bucket_script(keys=[key], args=[5, 10.0, 1.0, now_ms, 1])
    # Advance time by 1 second (10 tokens/sec refill).
    later_ms = now_ms + 1000
    result = token_bucket_script(keys=[key], args=[5, 10.0, 1.0, later_ms, 1])
    assert int(result[0]) == 1
    assert float(result[1]) >= 3
