"""Tests for aqp.ml.alpha_metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.ml.alpha_metrics import (
    combined_score,
    compute_alpha_metrics,
    compute_attribution,
    compute_trading_metrics,
)


def _series(values, n: int) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.Series(values, index=idx)


def test_compute_alpha_metrics_perfect_alignment() -> None:
    rng = np.random.default_rng(42)
    truth = rng.normal(size=200)
    pred = truth + rng.normal(scale=0.1, size=200)
    metrics = compute_alpha_metrics(_series(pred, 200), _series(truth, 200))

    assert metrics["n_predictions"] == 200
    assert metrics["n_labels_aligned"] == 200
    # IC should be very high since predictions are nearly equal to labels.
    assert metrics["ic_pearson"] > 0.95
    assert metrics["ic_spearman"] > 0.9
    assert 0.0 < metrics["rmse"] < 1.0
    # Hit rate should be near 1 for noise-aligned predictions.
    assert metrics["hit_rate"] > 0.9


def test_compute_alpha_metrics_handles_empty() -> None:
    metrics = compute_alpha_metrics(_series([np.nan, np.nan], 2), _series([np.nan, np.nan], 2))
    assert metrics["n_predictions"] == 2
    assert metrics["n_labels_aligned"] == 0
    # No correlations when there's no data.
    assert "rmse" not in metrics


def test_compute_trading_metrics_normalises_keys() -> None:
    summary = {
        "sharpe": "1.5",
        "sortino": 1.8,
        "max_drawdown": -0.12,
        "total_return": 0.25,
        "n_trades": 42,
        "turnover": 0.3,
        "calmar": "x",  # non-numeric coerces to 0
    }
    metrics = compute_trading_metrics(summary)
    assert metrics["sharpe"] == 1.5
    assert metrics["sortino"] == 1.8
    assert metrics["max_drawdown"] == -0.12
    assert metrics["total_return"] == 0.25
    assert metrics["n_trades"] == 42.0
    assert metrics["calmar"] == 0.0
    assert "turnover_adj_sharpe" in metrics


def test_compute_trading_metrics_with_equity_curve() -> None:
    ec = pd.Series(np.linspace(100, 130, 252), index=pd.date_range("2024-01-01", periods=252, freq="D"))
    metrics = compute_trading_metrics({}, equity_curve=ec)
    assert metrics["annualized_volatility"] >= 0
    # 30% absolute return over 1y -> annualized return roughly 0.3
    assert 0.2 < metrics["annualized_return"] < 0.5


def test_compute_attribution_handles_missing_inputs() -> None:
    out = compute_attribution(None, None)
    assert out == {"available": False}

    pred = _series([0.1, 0.2, 0.3], 3)
    timeline = {"trades": [{"vt_symbol": "AAA", "ts": "2024-01-01", "pnl": 1.0}]}
    out = compute_attribution(pred, timeline)
    assert out["available"] is True
    assert out["n_trades"] == 1
    assert out["total_pnl"] == 1.0


def test_combined_score_weights() -> None:
    ml = {"ic_spearman": 0.5, "icir": 0.4, "hit_rate": 0.6}
    tr = {"sharpe": 1.0, "calmar": 0.8}
    score = combined_score(ml, tr)
    # Sharpe weight 0.45 + icir 0.20 + ic 0.15 + hit 0.10 + calmar 0.10
    expected = 0.45 * 1.0 + 0.20 * 0.4 + 0.15 * 0.5 + 0.10 * 0.6 + 0.10 * 0.8
    assert abs(score - expected) < 1e-6


def test_combined_score_handles_missing() -> None:
    assert combined_score(None, None) == 0.0
    assert combined_score({"ic_spearman": 0.5}, None) == 0.075  # 0.15 * 0.5
