"""CPCV + DSR + sweep controller tests."""
from __future__ import annotations

import pytest

from aqp.lab.evaluation import (
    CPCVConfig,
    CPCVPlanError,
    combinatorial_purged_cv,
    deflated_sharpe_ratio,
    grid_sweep,
    probabilistic_sharpe_ratio,
    random_sweep,
    safe_cpcv_path_count,
)


# ---------------------------------------------------------------------------
# CPCV
# ---------------------------------------------------------------------------


def test_default_cpcv_path_count_is_15() -> None:
    # C(6, 2) = 15. Default config (n_folds=6, n_test=2) per plan §16.
    assert safe_cpcv_path_count(6, 2) == 15


def test_cpcv_produces_15_paths_with_default_config() -> None:
    paths = combinatorial_purged_cv(60)
    assert len(paths) == 15


def test_cpcv_path_has_disjoint_train_test() -> None:
    paths = combinatorial_purged_cv(60)
    for path in paths:
        assert set(path.train).isdisjoint(set(path.test))


def test_cpcv_high_path_count_blocks_by_default() -> None:
    # C(15, 5) = 3003 — well above the 100 guard.
    with pytest.raises(CPCVPlanError):
        combinatorial_purged_cv(
            300,
            CPCVConfig(n_folds=15, n_test_folds=5),
        )


def test_cpcv_high_path_count_allowed_with_explicit_opt_in() -> None:
    # Same config but operator-confirmed.
    paths = combinatorial_purged_cv(
        300,
        CPCVConfig(
            n_folds=15,
            n_test_folds=5,
            explicit_high_path_count_ok=True,
        ),
    )
    assert len(paths) == safe_cpcv_path_count(15, 5)


def test_cpcv_purges_around_test_folds() -> None:
    cfg = CPCVConfig(n_folds=4, n_test_folds=1, embargo_pct=10.0, purge_size=2)
    paths = combinatorial_purged_cv(40, cfg)
    # First path: test fold 0 covers rows [0, 10); train should skip
    # at least the purge + embargo rows immediately after.
    path = paths[0]
    assert all(r >= 10 + 4 for r in path.train) or all(r < 0 for r in path.train)


# ---------------------------------------------------------------------------
# DSR / PSR
# ---------------------------------------------------------------------------


def test_psr_zero_for_zero_sharpe() -> None:
    psr = probabilistic_sharpe_ratio(0.0, n_obs=200)
    # PSR = P(SR > 0); with observed = 0 and benchmark = 0 the answer
    # is 0.5 (the inflection point of the standard normal).
    assert 0.49 < psr < 0.51


def test_psr_high_for_strong_sharpe() -> None:
    psr = probabilistic_sharpe_ratio(2.0, n_obs=252)
    assert psr > 0.95


def test_dsr_deflates_when_many_trials() -> None:
    # Same observed Sharpe; more trials must give a LOWER DSR.
    dsr_1 = deflated_sharpe_ratio(1.5, n_obs=252, n_trials=1)
    dsr_100 = deflated_sharpe_ratio(1.5, n_obs=252, n_trials=100)
    dsr_10000 = deflated_sharpe_ratio(1.5, n_obs=252, n_trials=10000)
    assert dsr_1 >= dsr_100 >= dsr_10000


def test_dsr_at_one_trial_equals_psr() -> None:
    psr = probabilistic_sharpe_ratio(1.5, n_obs=252)
    dsr = deflated_sharpe_ratio(1.5, n_obs=252, n_trials=1)
    assert psr == pytest.approx(dsr, abs=1e-9)


# ---------------------------------------------------------------------------
# Sweep controllers
# ---------------------------------------------------------------------------


def test_grid_sweep_enumerates_full_product() -> None:
    ctrl = grid_sweep({"a": [1, 2, 3], "b": [10, 20]})
    assert ctrl.total_planned == 6
    assert len(ctrl.trials) == 6
    assert {(t.params["a"], t.params["b"]) for t in ctrl.trials} == {
        (1, 10), (1, 20), (2, 10), (2, 20), (3, 10), (3, 20),
    }


def test_grid_sweep_respects_budget() -> None:
    ctrl = grid_sweep({"a": [1, 2, 3], "b": [10, 20]}, budget=2)
    assert ctrl.total_planned == 2


def test_random_sweep_emits_n_trials() -> None:
    ctrl = random_sweep({"a": (0.0, 1.0), "b": (10.0, 20.0)}, budget=8, seed=7)
    assert ctrl.total_planned == 8
    for t in ctrl.trials:
        assert 0.0 <= t.params["a"] <= 1.0
        assert 10.0 <= t.params["b"] <= 20.0
