"""Smoke tests for the ML alpha models (skip when libs aren't installed)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

xgboost = pytest.importorskip("xgboost")


def _synthetic_bars(n_symbols: int = 3, n_days: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-02", periods=n_days, freq="B")
    rows = []
    for i in range(n_symbols):
        vt = f"SYM{i}.SIM"
        close = 100 * (1 + 0.001 * np.arange(n_days)) * (1 + rng.normal(0, 0.01, n_days)).cumprod()
        for t, p in zip(dates, close, strict=False):
            rows.append(
                {
                    "timestamp": t,
                    "vt_symbol": vt,
                    "open": p * 0.99,
                    "high": p * 1.01,
                    "low": p * 0.98,
                    "close": p,
                    "volume": 1_000_000,
                }
            )
    return pd.DataFrame(rows)


def test_xgboost_alpha_train_and_infer(tmp_path: Path):
    from aqp.strategies.ml_alphas import XGBoostAlpha

    bars = _synthetic_bars()
    model_path = tmp_path / "xgb_alpha.pkl"
    alpha = XGBoostAlpha(
        feature_specs=["SMA:10", "RSI:14", "Z:10"],
        model_path=model_path,
        long_threshold=0.0001,
        short_threshold=-0.0001,
    )
    metrics = alpha.train(bars, forward_horizon_days=5, n_estimators=50)
    assert metrics["n_rows"] > 0
    assert model_path.exists()
    # Inference
    from aqp.core.types import Symbol

    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse(v) for v in bars["vt_symbol"].unique()],
        context={},
    )
    assert isinstance(signals, list)
