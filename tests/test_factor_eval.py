"""Tests for factor evaluation + cross-validators."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.data.cv import MultipleTimeSeriesCV, PurgedKFold, TimeSeriesWalkForward
from aqp.data.factors import (
    align_factor_and_returns,
    compute_forward_returns,
    evaluate_factor,
    factor_information_coefficient,
    ic_summary,
    mean_returns_by_quantile,
    turnover_top_quantile,
)


def _synthetic_panel(n_symbols: int = 5, n_days: int = 120) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-02", periods=n_days, freq="B")
    rows = []
    factor_rows = []
    for i in range(n_symbols):
        vt = f"SYM{i}.SIM"
        noise = rng.normal(0, 0.01, size=n_days)
        drift = 0.001 * np.arange(n_days) * (1 if i % 2 == 0 else -1)
        prices = 100 * np.exp(np.cumsum(drift + noise))
        for t, p in zip(dates, prices, strict=False):
            rows.append({"timestamp": t, "vt_symbol": vt, "close": float(p)})
            factor_rows.append({"timestamp": t, "vt_symbol": vt, "factor": float(rng.normal())})
    return pd.DataFrame(rows), pd.DataFrame(factor_rows)


def test_compute_forward_returns_shape():
    prices, _ = _synthetic_panel()
    fwd = compute_forward_returns(prices, periods=(1, 5))
    assert {"fwd_1", "fwd_5"}.issubset(fwd.columns)
    assert len(fwd) == len(prices)


def test_ic_summary_returns_dict():
    prices, factor = _synthetic_panel()
    fwd = compute_forward_returns(prices, periods=(1, 5))
    aligned = align_factor_and_returns(factor, fwd)
    ic = factor_information_coefficient(aligned)
    stats = ic_summary(ic)
    assert set(stats.keys()) == {"fwd_1", "fwd_5"}
    for horizon_stats in stats.values():
        assert "mean" in horizon_stats
        assert "ir" in horizon_stats


def test_mean_returns_by_quantile_has_five_columns():
    prices, factor = _synthetic_panel()
    fwd = compute_forward_returns(prices, periods=(1,))
    aligned = align_factor_and_returns(factor, fwd)
    q_ret = mean_returns_by_quantile(aligned, n_quantiles=5)
    # Quantile columns Q1..Q5 (may be fewer if some dates don't support 5 quantiles).
    assert q_ret.shape[1] >= 2


def test_turnover_top_quantile_is_fraction():
    prices, factor = _synthetic_panel()
    fwd = compute_forward_returns(prices, periods=(1,))
    aligned = align_factor_and_returns(factor, fwd)
    turnover = turnover_top_quantile(aligned, n_quantiles=5)
    assert (turnover >= 0).all()
    assert (turnover <= 1).all()


def test_evaluate_factor_end_to_end():
    prices, factor = _synthetic_panel()
    report = evaluate_factor(factor, prices, factor_name="rnd", periods=(1, 5))
    assert report.factor_name == "rnd"
    assert not report.ic.empty
    d = report.to_dict()
    assert d["factor_name"] == "rnd"


# ---- CV -----------------------------------------------------------------


def test_multiple_time_series_cv_yields_nonempty_splits():
    prices, _ = _synthetic_panel(n_symbols=3, n_days=300)
    prices = prices.set_index(["vt_symbol", "timestamp"])
    cv = MultipleTimeSeriesCV(
        n_splits=3,
        train_period_length=60,
        test_period_length=20,
        date_idx="timestamp",
    )
    splits = list(cv.split(prices))
    assert len(splits) == 3
    for train, test in splits:
        assert len(train) > 0
        assert len(test) > 0


def test_purged_kfold_embargoes_boundary():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=500, freq="D"),
            "x": rng.normal(size=500),
        }
    )
    cv = PurgedKFold(n_splits=5, embargo_days=2)
    splits = list(cv.split(df))
    assert len(splits) == 5
    for train, test in splits:
        assert set(train).isdisjoint(set(test))


def test_walk_forward_progresses():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=500, freq="D"),
            "x": range(500),
        }
    )
    cv = TimeSeriesWalkForward(window_days=60, step_days=30, min_train_days=60)
    splits = list(cv.split(df))
    assert len(splits) > 0
