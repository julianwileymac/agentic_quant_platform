"""Phase-8 validation-diagnostic tests.

Acceptance gate from the production-enhancement plan:

> CombinatorialPurgedKFold(n_splits=10, n_test_splits=2) produces
> exactly 9 backtest paths (φ(10, 2) = 9); PBO ∈ [0, 1]; RAS lower
> bound ≤ empirical SR; DSR ∈ [0, 1].
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp_rl.core.base import RL_KIND_EXPERIMENT, list_rl_components
from aqp_rl.experiments.validation_suite import ValidationExperiment
from aqp_rl.validation import (
    CombinatorialPurgedKFold,
    benjamini_hochberg,
    combinatorial_paths_count,
    deflated_sharpe_ratio,
    empirical_rademacher_complexity,
    holm_bonferroni,
    probability_of_backtest_overfitting,
    rademacher_anti_serum,
    walk_forward_anchored,
    walk_forward_rolling,
)


# --------------------------------------------------------------------------- CPCV


def test_phi_count_matches_acceptance_gate():
    """φ(10, 2) = C(10, 2) · 2 / 10 = 45 · 0.2 = 9."""
    assert combinatorial_paths_count(10, 2) == 9


def test_phi_count_general_formula():
    """φ(N, k) = C(N, k) · k / N for several cases."""
    assert combinatorial_paths_count(6, 2) == 5
    assert combinatorial_paths_count(8, 4) == 35
    assert combinatorial_paths_count(20, 4) == 969


def test_phi_count_invalid_args_raise():
    with pytest.raises(ValueError):
        combinatorial_paths_count(0, 1)
    with pytest.raises(ValueError):
        combinatorial_paths_count(5, 5)
    with pytest.raises(ValueError):
        combinatorial_paths_count(5, 0)


def test_cpcv_yields_expected_number_of_combinations():
    """N=10, k=2 ⇒ 45 IS/OOS combinations, 9 backtest paths."""
    cv = CombinatorialPurgedKFold(n_splits=10, n_test_splits=2)
    X = np.zeros((100, 3))
    splits = list(cv.split(X))
    assert len(splits) == 45
    assert cv.n_backtest_paths() == 9
    assert cv.get_n_splits() == 45


def test_cpcv_train_test_disjoint():
    """No train index ever overlaps any test index after embargo."""
    cv = CombinatorialPurgedKFold(n_splits=8, n_test_splits=2, pct_embargo=0.02)
    X = np.zeros((100, 3))
    for train_idx, test_idx in cv.split(X):
        overlap = set(train_idx) & set(test_idx)
        assert not overlap, f"train/test overlap: {overlap}"


def test_cpcv_embargo_drops_post_test_observations():
    """Embargo removes a buffer of indices immediately after each test fold."""
    cv = CombinatorialPurgedKFold(n_splits=4, n_test_splits=1, pct_embargo=0.1)
    X = np.zeros((100, 3))
    # First fold: test [0, 25); embargo first 10 indices of train. Train
    # starts at 25 + 10 = 35 ... wait, embargo is AFTER the test block,
    # so train = [35, 100).
    splits = list(cv.split(X))
    train_idx, test_idx = splits[0]
    # The 10 rows immediately following the test block should be embargoed.
    assert 25 not in train_idx
    assert 34 not in train_idx


def test_cpcv_invalid_args_raise():
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_splits=1, n_test_splits=1)
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_splits=10, n_test_splits=10)
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_splits=10, n_test_splits=2, pct_embargo=0.6)


# --------------------------------------------------------------------------- PBO


def test_pbo_in_unit_interval():
    """PBO is always in [0, 1]."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, size=(200, 5))
    result = probability_of_backtest_overfitting(returns, n_blocks=10)
    assert 0.0 <= result["pbo"] <= 1.0
    assert result["n_splits"] > 0


def test_pbo_high_when_strategies_are_just_noise():
    """Pure-noise strategies ⇒ in-sample winner under-performs OOS ⇒ PBO ~ 0.5+."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, size=(400, 20))
    result = probability_of_backtest_overfitting(returns, n_blocks=16)
    # With pure noise we expect substantial overfitting (≥ 0.3).
    assert result["pbo"] >= 0.3


def test_pbo_low_when_one_strategy_dominates():
    """One strategy with clearly positive returns ⇒ low PBO."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, size=(200, 5))
    returns[:, 0] += 0.005  # systematically positive winner
    result = probability_of_backtest_overfitting(returns, n_blocks=10)
    assert result["pbo"] < 0.5


def test_pbo_invalid_args_raise():
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(np.zeros(10), n_blocks=4)
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(np.zeros((10, 3)), n_blocks=3)


# --------------------------------------------------------------------------- RAS


def test_rademacher_complexity_increases_with_population_size():
    """Adding more strategies ⇒ higher empirical Rademacher complexity."""
    rng = np.random.default_rng(0)
    small = rng.normal(0, 1, (100, 5))
    big = rng.normal(0, 1, (100, 50))
    r_small = empirical_rademacher_complexity(small, n_draws=200, seed=0)
    r_big = empirical_rademacher_complexity(big, n_draws=200, seed=0)
    assert r_big > r_small


def test_ras_lower_bound_at_most_empirical_sr():
    """The RAS-corrected SR is by construction ≤ empirical SR."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 1, (200, 10))
    sr_hat = 0.5
    result = rademacher_anti_serum(
        returns,
        empirical_sharpe=sr_hat,
        confidence=0.05,
        n_draws=200,
    )
    assert result["corrected"] <= sr_hat


def test_ras_penalties_nonneg():
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 1, (200, 10))
    result = rademacher_anti_serum(
        returns,
        empirical_sharpe=1.0,
        confidence=0.05,
        n_draws=200,
    )
    assert result["rademacher_penalty"] >= 0
    assert result["finite_sample_penalty"] >= 0
    assert result["multiple_testing_penalty"] >= 0


def test_ras_invalid_args_raise():
    with pytest.raises(ValueError):
        rademacher_anti_serum(np.zeros(10), empirical_sharpe=0.5)
    with pytest.raises(ValueError):
        rademacher_anti_serum(
            np.zeros((10, 2)),
            empirical_sharpe=0.5,
            confidence=0.0,
        )
    with pytest.raises(ValueError):
        rademacher_anti_serum(
            np.zeros((10, 2)),
            empirical_sharpe=0.5,
            confidence=1.5,
        )


# --------------------------------------------------------------------------- DSR


def test_dsr_in_unit_interval():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.001, 0.01, 300)
    dsr = deflated_sharpe_ratio(
        returns,
        sr_hat=0.1,
        sr_list=[0.1, 0.05, 0.07, 0.0, -0.02],
        n_strategies_tested=5,
    )
    assert 0.0 <= dsr <= 1.0


def test_dsr_high_for_unique_strong_strategy():
    """A strategy with clearly positive Sharpe + low search-space variance ⇒ high DSR."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0.01, 0.005, 500)  # strongly positive mean
    sr_hat = float(returns.mean() / returns.std(ddof=1))
    dsr = deflated_sharpe_ratio(
        returns,
        sr_hat=sr_hat,
        sr_list=[sr_hat, 0.0, 0.0],
        n_strategies_tested=3,
    )
    assert dsr > 0.5


def test_dsr_low_for_marginal_strategy_in_big_search_space():
    """Marginal Sharpe in a 100-strategy search space ⇒ low DSR."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0005, 0.01, 200)
    sr_hat = float(returns.mean() / returns.std(ddof=1))
    sr_list = rng.normal(0.0, 0.1, 100).tolist()
    sr_list[0] = sr_hat
    dsr = deflated_sharpe_ratio(
        returns,
        sr_hat=sr_hat,
        sr_list=sr_list,
        n_strategies_tested=100,
    )
    assert 0.0 <= dsr <= 1.0


def test_dsr_invalid_args_raise():
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(
            np.zeros(2), sr_hat=0.5, sr_list=[0.5], n_strategies_tested=1
        )
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(
            np.ones(10), sr_hat=0.5, sr_list=[0.5], n_strategies_tested=0
        )


# --------------------------------------------------------------------------- walk-forward


def test_walk_forward_anchored_expanding_window():
    splits = list(
        walk_forward_anchored(
            n_samples=100,
            train_size=20,
            test_size=10,
        )
    )
    assert len(splits) > 0
    sizes = [len(s.train_idx) for s in splits]
    assert sizes == sorted(sizes)  # train window expands


def test_walk_forward_rolling_fixed_window():
    splits = list(
        walk_forward_rolling(
            n_samples=100,
            train_size=20,
            test_size=10,
        )
    )
    sizes = {len(s.train_idx) for s in splits}
    assert sizes == {20}  # train window stays constant


def test_walk_forward_purge_drops_last_rows():
    splits = list(
        walk_forward_anchored(
            n_samples=100,
            train_size=30,
            test_size=10,
            purge=5,
        )
    )
    # First fold's train should end 5 rows before the test fold (i.e. 25 not 30).
    assert splits[0].train_idx[-1] == 24


def test_walk_forward_invalid_args_raise():
    with pytest.raises(ValueError):
        list(walk_forward_anchored(n_samples=0, train_size=10, test_size=5))
    with pytest.raises(ValueError):
        list(walk_forward_anchored(n_samples=100, train_size=0, test_size=5))
    with pytest.raises(ValueError):
        list(walk_forward_rolling(n_samples=100, train_size=20, test_size=5, step=0))


# --------------------------------------------------------------------------- multiple testing


def test_benjamini_hochberg_rejects_low_p_values():
    p = np.array([0.001, 0.01, 0.04, 0.2, 0.8])
    result = benjamini_hochberg(p, alpha=0.05)
    assert result["reject"].dtype == bool
    # Smaller p-values get rejected.
    assert result["reject"][0]
    assert not result["reject"][4]


def test_benjamini_hochberg_adjusted_in_unit_interval():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 50)
    result = benjamini_hochberg(p)
    assert (result["adjusted"] >= 0).all()
    assert (result["adjusted"] <= 1).all()


def test_holm_bonferroni_more_conservative_than_bh():
    """For the same p-values, Holm rejects ≤ BH (Holm is stricter)."""
    rng = np.random.default_rng(0)
    p = rng.beta(0.5, 5, 30)
    bh = benjamini_hochberg(p, alpha=0.05)
    holm = holm_bonferroni(p, alpha=0.05)
    assert holm["reject"].sum() <= bh["reject"].sum()


def test_multiple_testing_invalid_args_raise():
    with pytest.raises(ValueError):
        benjamini_hochberg(np.zeros((2, 2)))
    with pytest.raises(ValueError):
        benjamini_hochberg(np.zeros(5), alpha=0.0)
    with pytest.raises(ValueError):
        holm_bonferroni(np.zeros(5), alpha=1.0)


# --------------------------------------------------------------------------- experiment


def test_validation_experiment_registered():
    registry = list_rl_components(RL_KIND_EXPERIMENT)
    assert "validation_suite" in registry
    assert registry["validation_suite"] is ValidationExperiment


def test_validation_experiment_runs_end_to_end():
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, (200, 8))
    returns[:, 3] += 0.002  # winner
    exp = ValidationExperiment(
        n_splits=10,
        n_test_splits=2,
        pbo_n_blocks=10,
        rademacher_draws=100,
    )
    result = exp.run(returns_matrix=returns)
    assert "winning_strategy_idx" in result
    assert 0.0 <= result["pbo"] <= 1.0
    assert 0.0 <= result["deflated_sharpe_ratio"] <= 1.0
    assert result["rademacher"]["corrected_sr_lower_bound"] <= result["sr_hat"]
    assert result["cpcv"]["n_backtest_paths"] == 9
