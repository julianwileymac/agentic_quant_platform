"""Differential Downside Deviation Ratio (D3R) — unit tests."""
from __future__ import annotations

import pytest

from aqp_rl.core.base import RL_KIND_REWARD, list_rl_components
from aqp_rl.rewards.differential_downside import DifferentialDownside


def _step(term: DifferentialDownside, ret: float) -> float:
    return term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 100.0 * (1.0 + ret)},
        info={"portfolio_return": ret},
    )


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_REWARD)
    assert "differential_downside" in registry
    assert registry["differential_downside"] is DifferentialDownside


def test_pure_upside_yields_zero_d3r():
    """All-positive returns ⇒ no downside variance ⇒ zero reward."""
    term = DifferentialDownside(eta=0.05, warmup=2)
    rewards = [_step(term, 0.01) for _ in range(100)]
    assert all(r == 0.0 for r in rewards)
    assert term.current_sortino() == 0.0


def test_negative_returns_eventually_produce_finite_d3r():
    """Sequence of mixed returns including downside ⇒ D3R becomes finite."""
    term = DifferentialDownside(eta=0.1, warmup=0)
    # Inject some downside variance.
    for _ in range(10):
        _step(term, -0.02)
    # Now mixed returns should produce a non-zero D3R most steps.
    nonzero = 0
    for _ in range(50):
        out = _step(term, -0.01 if nonzero % 2 == 0 else 0.005)
        if out != 0.0:
            nonzero += 1
    assert nonzero > 5


def test_reset_clears_state():
    term = DifferentialDownside(eta=0.1, warmup=0)
    for _ in range(20):
        _step(term, -0.01)
    assert term._DD > 0  # noqa: SLF001
    term.reset()
    assert term._A == 0.0  # noqa: SLF001
    assert term._DD == 0.0  # noqa: SLF001
    assert term._t == 0  # noqa: SLF001


def test_target_return_adjusts_downside_definition():
    """Returns above target_return don't count as downside."""
    term = DifferentialDownside(eta=0.1, warmup=0, target_return=0.005)
    # Returns of 0.003 are below target=0.005, so they ARE downside.
    rewards = [_step(term, 0.003) for _ in range(30)]
    # Some non-zero contributions expected once DD has accumulated.
    assert any(r != 0.0 for r in rewards[5:])


def test_invalid_eta_raises():
    with pytest.raises(ValueError):
        DifferentialDownside(eta=0.0)
    with pytest.raises(ValueError):
        DifferentialDownside(eta=1.0)
