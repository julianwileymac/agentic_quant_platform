"""Hermetic tests for the in-memory strategy.

These tests do NOT touch Redis. They exercise the bucket math,
reservation lifecycle, and per-agent dual-debit semantics so the
contract that the Lua script must respect is pinned in Python.
"""
from __future__ import annotations

import time

import pytest

from aqp_ratelimit.strategies.in_memory import InMemoryStrategy
from aqp_ratelimit.strategies.per_agent import PerAgentStrategy


def test_check_allows_until_capacity_exhausted():
    strategy = InMemoryStrategy(capacity=5, refill_rate=0.1)
    for _ in range(5):
        decision = strategy.check(
            user_id="u1", service="polygon.aggregates", key_id="primary"
        )
        assert decision.allow is True
    decision = strategy.check(
        user_id="u1", service="polygon.aggregates", key_id="primary"
    )
    assert decision.allow is False
    assert decision.retry_after_ms > 0


def test_check_isolates_buckets_per_user():
    strategy = InMemoryStrategy(capacity=1, refill_rate=0.0)
    a = strategy.check(user_id="alice", service="polygon", key_id="primary")
    b = strategy.check(user_id="bob", service="polygon", key_id="primary")
    assert a.allow is True
    assert b.allow is True


def test_check_isolates_buckets_per_key_id():
    strategy = InMemoryStrategy(capacity=1, refill_rate=0.0)
    a = strategy.check(user_id="u1", service="polygon", key_id="primary")
    b = strategy.check(user_id="u1", service="polygon", key_id="backup")
    assert a.allow is True
    assert b.allow is True


def test_reserve_then_release_returns_tokens():
    strategy = InMemoryStrategy(capacity=10, refill_rate=0.0)
    outcome = strategy.reserve(
        user_id="u1",
        service="polygon",
        key_id="primary",
        n_tokens=6,
        ttl_s=60,
    )
    assert outcome.allow is True
    assert outcome.reservation_id is not None
    after = strategy.status(user_id="u1", service="polygon", key_id="primary")
    assert after.remaining == pytest.approx(4)
    strategy.release(reservation_id=outcome.reservation_id)
    refunded = strategy.status(user_id="u1", service="polygon", key_id="primary")
    assert refunded.remaining == pytest.approx(10)


def test_reserve_rejects_when_capacity_insufficient():
    strategy = InMemoryStrategy(capacity=5, refill_rate=0.0)
    outcome = strategy.reserve(
        user_id="u1",
        service="polygon",
        key_id="primary",
        n_tokens=10,
        ttl_s=60,
    )
    assert outcome.allow is False
    assert outcome.reservation_id is None
    assert outcome.requested == 10
    assert outcome.remaining == pytest.approx(5)


def test_refill_replenishes_tokens_over_time():
    strategy = InMemoryStrategy(capacity=5, refill_rate=100.0)
    for _ in range(5):
        strategy.check(user_id="u1", service="polygon", key_id="primary")
    time.sleep(0.1)
    decision = strategy.check(user_id="u1", service="polygon", key_id="primary")
    assert decision.allow is True


def test_per_agent_wrapper_dual_debits():
    inner = InMemoryStrategy(capacity=10, refill_rate=0.0)
    wrapper = PerAgentStrategy(inner=inner)

    user_only = wrapper.check(
        user_id="u1",
        service="polygon",
        key_id="primary",
        n_tokens=1,
        ctx={"actor_kind": "user"},
    )
    assert user_only.allow is True

    agent = wrapper.check(
        user_id="u1",
        service="polygon",
        key_id="primary",
        n_tokens=1,
        ctx={"actor_kind": "agent", "agent_subject": "agent|preview"},
    )
    assert agent.allow is True

    inner_status = inner.status(user_id="u1", service="polygon", key_id="primary")
    assert inner_status.remaining == pytest.approx(8)
    agent_status = inner.status(
        user_id="__agent__agent|preview",
        service="polygon",
        key_id="agent:agent|preview",
    )
    assert agent_status.remaining < agent_status.capacity
