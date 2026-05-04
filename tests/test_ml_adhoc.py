"""Tests for the aqp.ml.adhoc notebook helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_panel() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 200
    return pd.DataFrame(
        {
            "f1": rng.normal(size=n),
            "f2": rng.normal(size=n),
            "f3": rng.normal(size=n),
        }
    )


@pytest.fixture
def synthetic_target(synthetic_panel: pd.DataFrame) -> pd.Series:
    rng = np.random.default_rng(7)
    # Linear combination + noise — quick_ridge should pick this up.
    return (
        2.0 * synthetic_panel["f1"]
        - 0.5 * synthetic_panel["f2"]
        + 0.1 * rng.normal(size=len(synthetic_panel))
    )


def test_quick_ridge_fits(synthetic_panel: pd.DataFrame, synthetic_target: pd.Series) -> None:
    pytest.importorskip("sklearn")
    from aqp.ml.adhoc.regression import quick_ridge

    out = quick_ridge(synthetic_panel, synthetic_target, alpha=1.0)
    assert out.estimator == "ridge"
    assert out.n_train == len(synthetic_panel)
    assert out.n_features == 3
    # f1 coefficient should be the largest.
    assert out.coefficients["f1"] > out.coefficients["f2"]
    assert out.score > 0.5


def test_quick_elasticnet_fits(
    synthetic_panel: pd.DataFrame, synthetic_target: pd.Series
) -> None:
    pytest.importorskip("sklearn")
    from aqp.ml.adhoc.regression import quick_elasticnet

    out = quick_elasticnet(synthetic_panel, synthetic_target, alpha=0.1)
    assert out.estimator == "elasticnet"
    assert out.n_features == 3


def test_quick_panel_fixed_effects(synthetic_panel: pd.DataFrame) -> None:
    pytest.importorskip("sklearn")
    from aqp.ml.adhoc.regression import quick_panel_fixed_effects

    panel = synthetic_panel.copy()
    panel["vt_symbol"] = ["AAA"] * 100 + ["BBB"] * 100
    panel["y"] = panel["f1"] * 2.0
    out = quick_panel_fixed_effects(
        panel,
        target_col="y",
        entity_col="vt_symbol",
        feature_cols=["f1", "f2"],
    )
    assert out.estimator == "panel_fixed_effects"
    # Within-entity slope should still recover ~2 on f1.
    assert abs(out.coefficients["f1"] - 2.0) < 0.1


def test_quick_naive_baseline_strategies() -> None:
    series = pd.Series(
        np.linspace(0, 10, 100),
        index=pd.date_range("2024-01-01", periods=100, freq="D"),
    )
    from aqp.ml.adhoc.forecast import quick_naive_baseline

    last = quick_naive_baseline(series, horizon=5, strategy="last")
    assert all(last.forecast.values == 10.0)
    mean = quick_naive_baseline(series, horizon=5, strategy="mean")
    assert all(abs(v - 5.0) < 0.1 for v in mean.forecast.values)
    drift = quick_naive_baseline(series, horizon=5, strategy="drift")
    # Drift continues the trend — should be > 10
    assert drift.forecast.iloc[-1] > 10.0


def test_quick_arima_runs() -> None:
    pytest.importorskip("statsmodels")
    rng = np.random.default_rng(0)
    series = pd.Series(
        rng.normal(size=200).cumsum(),
        index=pd.date_range("2024-01-01", periods=200, freq="D"),
    )
    from aqp.ml.adhoc.timeseries import quick_arima

    out = quick_arima(series, horizon=5, order=(1, 1, 0))
    assert out.backend == "arima"
    assert out.horizon == 5
    assert len(out.forecast) == 5
    assert out.metrics["aic"] != 0


def test_quick_decompose_handles_short_series() -> None:
    pytest.importorskip("statsmodels")
    series = pd.Series(
        np.arange(5),
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )
    from aqp.ml.adhoc.timeseries import quick_decompose

    out = quick_decompose(series, period=20)
    assert out.period == 20
    assert len(out.rows) == 5  # only "observed" column when too short
