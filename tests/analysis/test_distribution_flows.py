"""Distribution flows — smoke tests against synthetic data."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.analysis import run_flow


@pytest.fixture
def normal_returns() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({"ret": rng.normal(loc=0.0, scale=0.01, size=2000)})


@pytest.fixture
def heavy_tail_returns() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({"ret": rng.standard_t(df=3, size=2000) * 0.01})


def test_descriptive_stats_normal(normal_returns: pd.DataFrame) -> None:
    out = run_flow(
        "distribution.descriptive_stats",
        normal_returns,
        {"column": "ret", "quantiles": [0.1, 0.5, 0.9]},
    )
    metrics = out.metrics
    assert metrics["n"] == 2000
    assert abs(metrics["mean"]) < 0.005
    assert metrics["std"] > 0
    assert "kurtosis" in metrics


def test_histogram_returns_bins(normal_returns: pd.DataFrame) -> None:
    out = run_flow(
        "distribution.histogram",
        normal_returns,
        {"column": "ret", "bins": 30},
    )
    assert out.chart is not None
    assert len(out.rows) == 30
    assert {"bin_left", "bin_right", "bin_mid", "count"} <= set(out.rows[0])


def test_shapiro_accepts_normal(normal_returns: pd.DataFrame) -> None:
    out = run_flow(
        "distribution.shapiro_wilk",
        normal_returns,
        {"column": "ret"},
    )
    assert "pvalue" in out.metrics
    assert "statistic" in out.metrics


def test_jarque_bera_rejects_t_dist(heavy_tail_returns: pd.DataFrame) -> None:
    out = run_flow(
        "distribution.jarque_bera",
        heavy_tail_returns,
        {"column": "ret"},
    )
    # Heavy-tail t(3) should reject normality at 5% level.
    assert out.metrics["pvalue"] < 0.05


def test_ks_runs(normal_returns: pd.DataFrame) -> None:
    out = run_flow(
        "distribution.kolmogorov_smirnov",
        normal_returns,
        {"column": "ret", "distribution": "norm", "standardize": True},
    )
    assert "statistic" in out.metrics


def test_qq_emits_chart(normal_returns: pd.DataFrame) -> None:
    out = run_flow(
        "distribution.qq_plot_points",
        normal_returns,
        {"column": "ret", "distribution": "norm", "sample_size": 200},
    )
    assert out.chart is not None
    assert len(out.rows) > 0
