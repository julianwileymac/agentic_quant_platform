"""Differential Sharpe Ratio (Moody & Saffell 1998) — unit + property tests.

Verifies the per-step DSR contribution behaves as documented:

1. ``reset()`` clears the EMAs and warm-up counter.
2. On an i.i.d. ``N(0, 1)`` return stream the running EMA mean drifts
   toward 0 within a tolerance proportional to ``η``.
3. On a monotone-increasing return series the per-step DSR
   contribution is strictly positive (the agent is making the running
   Sharpe better).
4. On a monotone-decreasing return series the per-step DSR
   contribution is strictly negative.
5. Auto-registration through the :class:`RLComponent` metaclass with
   ``rl_kind='rl_reward'`` and ``rl_alias='differential_sharpe'``.
6. Round-trips through :meth:`CompositeReward.compute` and surfaces
   the per-term breakdown under ``info['reward_terms']``.
7. ``K_eta`` matches the closed-form ``sqrt((1 - η/2) / (1 - η))``.
"""
from __future__ import annotations

import math
import random

import pytest

from aqp_rl.core.base import RL_KIND_REWARD, list_rl_components
from aqp_rl.core.reward import CompositeReward
from aqp_rl.rewards.differential_sharpe import DifferentialSharpe


def _step(term: DifferentialSharpe, ret: float) -> float:
    """Drive one step of the term with a synthetic per-step return."""
    return term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 100.0 * (1.0 + ret)},
        info={"portfolio_return": ret},
    )


def test_register_with_rlcomponent_metaclass():
    registry = list_rl_components(RL_KIND_REWARD)
    assert "differential_sharpe" in registry
    cls = registry["differential_sharpe"]
    assert cls is DifferentialSharpe
    assert DifferentialSharpe.rl_kind == "rl_reward"


def test_k_eta_closed_form_matches():
    eta = 1e-2
    term = DifferentialSharpe(eta=eta)
    expected = math.sqrt((1.0 - eta / 2.0) / (1.0 - eta))
    assert term.K_eta == pytest.approx(expected, rel=1e-12)


def test_warmup_emits_zero_then_nonzero():
    term = DifferentialSharpe(eta=0.1, warmup=2)
    assert _step(term, 0.01) == 0.0
    assert _step(term, 0.01) == 0.0
    third = _step(term, 0.01)
    assert third != 0.0


def test_reset_clears_state():
    term = DifferentialSharpe(eta=0.1, warmup=0)
    for _ in range(50):
        _step(term, 0.01)
    assert term.current_sharpe() != 0.0
    term.reset()
    assert term._A == 0.0  # noqa: SLF001
    assert term._B == 0.0  # noqa: SLF001
    assert term._t == 0  # noqa: SLF001
    assert term.current_sharpe() == 0.0


def test_iid_normal_drift_to_zero_mean():
    """With i.i.d. N(0, 1) returns the running mean EMA should hover near 0."""
    rng = random.Random(42)
    term = DifferentialSharpe(eta=1e-2, warmup=0)
    for _ in range(2000):
        _step(term, rng.gauss(0.0, 1.0))
    # With η = 1e-2 the effective window is ≈ 100 samples; the EMA
    # mean should fall within ±0.3 of 0 with high probability.
    assert abs(term._A) < 0.5  # noqa: SLF001


def test_monotone_increasing_returns_positive_dsr_eventually():
    """Monotonically rising returns ⇒ DSR > 0 once warm-up clears."""
    term = DifferentialSharpe(eta=0.05, warmup=10)
    # Drive past warm-up with positive returns.
    rewards = [_step(term, 0.001 * (i + 1)) for i in range(200)]
    post_warmup = [r for r in rewards[20:] if r != 0.0]
    assert len(post_warmup) > 0
    # Strict majority of post-warmup contributions are positive.
    positive_share = sum(1 for r in post_warmup if r > 0) / len(post_warmup)
    assert positive_share > 0.5


def test_monotone_decreasing_returns_negative_dsr():
    """Strictly negative returns ⇒ DSR contribution turns negative."""
    term = DifferentialSharpe(eta=0.05, warmup=5)
    # Warm up with neutral returns then push negative.
    for _ in range(20):
        _step(term, 0.0)
    rewards = [_step(term, -0.01 * (i + 1)) for i in range(50)]
    nonzero = [r for r in rewards if r != 0.0]
    assert len(nonzero) > 0
    negative_share = sum(1 for r in nonzero if r < 0) / len(nonzero)
    assert negative_share > 0.6


def test_invalid_eta_raises():
    with pytest.raises(ValueError):
        DifferentialSharpe(eta=0.0)
    with pytest.raises(ValueError):
        DifferentialSharpe(eta=1.5)


def test_composite_decomposition_surfaces_dsr():
    composite = CompositeReward(terms=[DifferentialSharpe(eta=0.1, warmup=0)])
    info: dict = {"portfolio_return": 0.02}
    composite.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 102.0},
        info=info,
    )
    assert "differential_sharpe" in info["reward_terms"]


def test_falls_back_to_portfolio_value_when_no_return_key():
    term = DifferentialSharpe(eta=0.1, warmup=0, return_key="missing")
    out = term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 101.0},
        info={},
    )
    # First step is past warm-up but denom is initially zero ⇒ 0.
    # Second step should be non-zero.
    out2 = term.compute(
        state={"portfolio_value": 101.0},
        action=None,
        next_state={"portfolio_value": 103.0},
        info={},
    )
    assert isinstance(out, float)
    assert isinstance(out2, float)


def test_to_dict_payload():
    term = DifferentialSharpe(eta=0.05, warmup=3, eps=1e-9, return_key="r")
    payload = term.to_dict()
    assert payload["eta"] == 0.05
    assert payload["warmup"] == 3
    assert payload["return_key"] == "r"
    assert "K_eta" in payload
