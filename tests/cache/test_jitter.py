"""Tests for the TTL jitter helper introduced in Phase 0."""
from __future__ import annotations

import pytest

from aqp.cache.client import jitter_ttl
from aqp.config import settings


def test_jitter_respects_minimum_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_ttl_jitter_pct", 0)
    assert jitter_ttl(5) == 60  # 5s requested, floored to 60s


def test_jitter_zero_pct_is_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_ttl_jitter_pct", 0)
    assert jitter_ttl(300) == 300


def test_jitter_within_pct_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_ttl_jitter_pct", 10)
    base = 300
    for _ in range(100):
        out = jitter_ttl(base)
        assert base <= out <= int(base * 1.10)


def test_jitter_explicit_pct_overrides_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_ttl_jitter_pct", 0)
    base = 600
    for _ in range(100):
        out = jitter_ttl(base, pct=25)
        assert base <= out <= int(base * 1.25)


def test_jitter_pct_clamped_to_50() -> None:
    """Settings overrides above 50% are clamped (avoids absurd spreads)."""
    base = 100
    for _ in range(20):
        out = jitter_ttl(base, pct=200)  # 200% gets clamped to 50%
        assert base <= out <= int(base * 1.5)
