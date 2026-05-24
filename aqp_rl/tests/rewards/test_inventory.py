"""Running inventory penalty (Cartea-Jaimungal full) — unit tests."""
from __future__ import annotations

import pytest

from aqp_rl.core.base import RL_KIND_REWARD, list_rl_components
from aqp_rl.rewards.inventory import RunningInventoryPenalty


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_REWARD)
    assert "running_inventory" in registry
    assert registry["running_inventory"] is RunningInventoryPenalty


def test_zero_inventory_yields_pnl_only():
    """Flat position ⇒ no penalty, only PnL contribution."""
    term = RunningInventoryPenalty(phi=1e-3, alpha=1e-2)
    out = term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 110.0},
        info={"inventory": 0},
    )
    # Penalty = 0 (I = 0); PnL contribution = +10
    assert out == pytest.approx(10.0)


def test_running_penalty_scales_with_phi_and_i_squared():
    """Running penalty ``-φ · I² · Δt``."""
    term = RunningInventoryPenalty(phi=0.01, alpha=0.0, dt=1.0, include_pnl=False)
    info = {"inventory": 10}
    out = term.compute(state={}, action=None, next_state={}, info=info)
    # -0.01 * 100 * 1 = -1.0
    assert out == pytest.approx(-1.0)


def test_terminal_penalty_only_fires_at_terminal():
    """``α · I_T²`` only contributes when ``info['terminated']`` is True."""
    term = RunningInventoryPenalty(phi=0.0, alpha=0.5, include_pnl=False)
    info_running = {"inventory": 10, "terminated": False}
    info_terminal = {"inventory": 10, "terminated": True}
    out_running = term.compute(state={}, action=None, next_state={}, info=info_running)
    out_terminal = term.compute(state={}, action=None, next_state={}, info=info_terminal)
    assert out_running == 0.0
    # -0.5 * 100 = -50
    assert out_terminal == pytest.approx(-50.0)


def test_is_terminal_key_also_recognised():
    """``info['is_terminal']`` is an accepted alias for ``info['terminated']``."""
    term = RunningInventoryPenalty(phi=0.0, alpha=0.5, include_pnl=False)
    info_alias = {"inventory": 4, "is_terminal": True}
    out = term.compute(state={}, action=None, next_state={}, info=info_alias)
    # -0.5 * 16 = -8
    assert out == pytest.approx(-8.0)


def test_pnl_inclusion_toggle():
    term_with = RunningInventoryPenalty(phi=0.0, alpha=0.0, include_pnl=True)
    term_without = RunningInventoryPenalty(phi=0.0, alpha=0.0, include_pnl=False)
    state = {"portfolio_value": 100.0}
    next_state = {"portfolio_value": 120.0}
    info = {"inventory": 0}
    assert term_with.compute(state=state, action=None, next_state=next_state, info=info) == pytest.approx(20.0)
    assert term_without.compute(state=state, action=None, next_state=next_state, info=info) == 0.0


def test_invalid_params_raise():
    with pytest.raises(ValueError):
        RunningInventoryPenalty(phi=-1.0)
    with pytest.raises(ValueError):
        RunningInventoryPenalty(alpha=-1.0)
    with pytest.raises(ValueError):
        RunningInventoryPenalty(dt=0.0)


def test_inventory_falls_back_to_next_state():
    """When ``info['inventory']`` is missing, falls back to ``next_state['inventory']``."""
    term = RunningInventoryPenalty(phi=0.01, alpha=0.0, include_pnl=False)
    out = term.compute(state={}, action=None, next_state={"inventory": 5}, info={})
    # -0.01 * 25 = -0.25
    assert out == pytest.approx(-0.25)
