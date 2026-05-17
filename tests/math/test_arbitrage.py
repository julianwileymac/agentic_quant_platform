"""Tests for the Phase 4 statistical-arbitrage math primitives."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.math.arbitrage import (
    BasisResult,
    SignalKind,
    adr_basis,
    ah_share_basis,
    half_life,
    pair_signal,
    rolling_zscore,
)


# ---------------------------------------------------------------------------
# Rolling z-score
# ---------------------------------------------------------------------------


def test_rolling_zscore_nan_for_warmup_window():
    """The first ``window-1`` observations should be NaN."""
    s = pd.Series([1.0] * 10 + [2.0] * 10)
    z = rolling_zscore(s, window=5)
    assert z.iloc[:4].isna().all()
    assert not z.iloc[5:].isna().all()


def test_rolling_zscore_on_constant_yields_zero_or_nan():
    s = pd.Series([1.0] * 20)
    z = rolling_zscore(s, window=5)
    # std=0 leads to NaN (division by zero); the test asserts we don't
    # crash and the result is bounded
    z_clean = z.dropna()
    # Either no values survive (all NaN from div-by-zero) or zero
    assert all(abs(v) < 1e-9 or np.isnan(v) for v in z_clean)


# ---------------------------------------------------------------------------
# Half-life
# ---------------------------------------------------------------------------


def test_half_life_on_mean_reverting_series_is_finite():
    """A mean-reverting AR(1) process has finite half-life."""
    rng = np.random.default_rng(seed=42)
    n = 500
    s = np.zeros(n)
    mu = 10.0
    theta = 0.05
    sigma = 0.1
    for i in range(1, n):
        s[i] = s[i - 1] + theta * (mu - s[i - 1]) + rng.normal(0, sigma)
    spread = pd.Series(s + mu)
    result = half_life(spread)
    assert result.is_stationary
    assert 0 < result.half_life < float("inf")


def test_half_life_on_random_walk_returns_infinity():
    """A pure random walk is not mean-reverting -> infinity."""
    rng = np.random.default_rng(seed=7)
    s = pd.Series(np.cumsum(rng.normal(0, 1, 500)))
    result = half_life(s)
    # Random walk may have noisy theta near zero; accept either
    # "not stationary" or "very long half life"
    assert not result.is_stationary or result.half_life > 200


def test_half_life_too_few_observations():
    """A 10-row series returns infinite half-life and is_stationary=False."""
    s = pd.Series([1.0, 2.0, 1.5, 1.7, 1.3, 1.8, 1.6, 1.5, 1.7, 1.4])
    result = half_life(s)
    assert result.is_stationary is False
    assert result.half_life == float("inf")


# ---------------------------------------------------------------------------
# Pair signal
# ---------------------------------------------------------------------------


def test_pair_signal_entry_long_at_high_zscore():
    """Spread with z >> 0 returns ENTRY_LONG_SPREAD."""
    rng = np.random.default_rng(seed=123)
    base = rng.normal(0.0, 1.0, 200)
    base[-1] = 10.0  # latest is way above mean
    spread = pd.Series(base)
    signal = pair_signal(spread, entry_threshold=2.0, window=50)
    assert signal.kind is SignalKind.ENTRY_LONG_SPREAD
    assert signal.zscore > 2.0


def test_pair_signal_entry_short_at_low_zscore():
    """Spread with z << 0 returns ENTRY_SHORT_SPREAD."""
    rng = np.random.default_rng(seed=456)
    base = rng.normal(0.0, 1.0, 200)
    base[-1] = -10.0
    spread = pd.Series(base)
    signal = pair_signal(spread, entry_threshold=2.0, window=50)
    assert signal.kind is SignalKind.ENTRY_SHORT_SPREAD


def test_pair_signal_hold_in_neutral_band():
    """Spread inside ``entry_threshold`` returns HOLD."""
    spread = pd.Series([0.1] * 100)
    signal = pair_signal(spread, entry_threshold=2.0, window=20)
    assert signal.kind is SignalKind.HOLD


def test_pair_signal_exit_when_position_reverts():
    """In-position + z within exit band returns EXIT signal."""
    rng = np.random.default_rng(seed=789)
    base = rng.normal(0.0, 1.0, 200)
    base[-1] = 0.1  # within exit band
    spread = pd.Series(base)
    signal = pair_signal(
        spread, entry_threshold=2.0, exit_threshold=0.5, window=50, is_in_position=True
    )
    assert signal.kind in (SignalKind.EXIT_LONG_SPREAD, SignalKind.EXIT_SHORT_SPREAD)


# ---------------------------------------------------------------------------
# A/H share basis
# ---------------------------------------------------------------------------


def test_ah_share_basis_no_arbitrage_within_tolerance():
    """A-share + H-share at fair-value FX produce zero basis."""
    # ICBC: A in CNY ~ 5.0; CNY/HKD ~ 0.93 -> implied H ~ 5.37 HKD
    res = ah_share_basis(
        a_price=5.0,
        h_price=5.37,
        fx_rate=0.93,
        conversion_ratio=1.0,
        threshold_bps=100.0,
    )
    assert abs(res.basis_pct) < 0.01
    assert res.is_arbitrage is False


def test_ah_share_basis_flags_h_premium():
    """When H-share trades at a meaningful premium, flags the direction."""
    res = ah_share_basis(
        a_price=5.0,
        h_price=6.0,  # H rich vs implied 5.37
        fx_rate=0.93,
        conversion_ratio=1.0,
        threshold_bps=100.0,
    )
    assert res.is_arbitrage is True
    # H is rich -> sell H, buy A (which is cheap)
    # The sign of basis = h - implied_h > 0 -> direction "buy_a_sell_b"
    assert res.arbitrage_direction == "buy_a_sell_b"


def test_ah_share_basis_flags_a_premium():
    """When A-share trades at a meaningful premium, flags reversed direction."""
    res = ah_share_basis(
        a_price=6.0,
        h_price=5.0,  # H cheap vs implied 6.45
        fx_rate=0.93,
        conversion_ratio=1.0,
        threshold_bps=100.0,
    )
    assert res.is_arbitrage is True
    # H is cheap -> buy H, sell A
    assert res.arbitrage_direction == "buy_b_sell_a"


def test_ah_share_basis_rejects_invalid_fx():
    with pytest.raises(ValueError):
        ah_share_basis(a_price=5.0, h_price=5.0, fx_rate=0.0)


# ---------------------------------------------------------------------------
# ADR basis
# ---------------------------------------------------------------------------


def test_adr_basis_at_fair_value():
    """ADR at fair-value vs underlying produces basis ~ 0."""
    # BABA: 1 ADR = 8 H-shares (HKEX 9988). Underlying in HKD, ADR in USD.
    # Fair USD price = (HKD price / fx_rate * conversion_ratio)
    res = adr_basis(
        adr_price=100.0,
        underlying_price=98.0,
        fx_rate=7.84,
        conversion_ratio=8.0,
        threshold_bps=80.0,
    )
    assert abs(res.basis_pct) < 0.02
    assert res.is_arbitrage is False


def test_adr_basis_flags_adr_premium():
    """ADR trading rich -> sell_adr_buy_underlying."""
    res = adr_basis(
        adr_price=120.0,
        underlying_price=98.0,
        fx_rate=7.84,
        conversion_ratio=8.0,
        threshold_bps=80.0,
    )
    assert res.is_arbitrage is True
    assert res.arbitrage_direction == "sell_adr_buy_underlying"


def test_adr_basis_flags_adr_discount():
    """ADR trading cheap -> buy_adr_sell_underlying."""
    res = adr_basis(
        adr_price=80.0,
        underlying_price=98.0,
        fx_rate=7.84,
        conversion_ratio=8.0,
        threshold_bps=80.0,
    )
    assert res.is_arbitrage is True
    assert res.arbitrage_direction == "buy_adr_sell_underlying"


def test_adr_basis_cost_adjustment_reduces_signal_strength():
    """Total cost (transaction + depository) is subtracted from raw basis."""
    res = adr_basis(
        adr_price=120.0,
        underlying_price=98.0,
        fx_rate=7.84,
        conversion_ratio=8.0,
        transaction_cost_bps=100.0,
        depository_fee_bps=20.0,
    )
    # raw_basis > cost_adjusted_basis
    assert res.basis > res.cost_adjusted_basis
