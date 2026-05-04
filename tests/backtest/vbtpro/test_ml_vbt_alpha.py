"""Tests for MLVbtAlpha — uses a deterministic dummy model."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.backtest.vbtpro.signal_builder import SignalArrays
from aqp.core.types import Symbol
from aqp.strategies.vbtpro.ml_alpha import MLVbtAlpha


class _DummyModel:
    """Returns ``close * coef + bias`` so we know exactly what to expect."""

    def __init__(self, coef: float = 0.01, bias: float = -1.0) -> None:
        self.coef = coef
        self.bias = bias

    def predict(self, X) -> np.ndarray:
        if hasattr(X, "values"):
            arr = X.values
        else:
            arr = np.asarray(X)
        if arr.ndim == 2:
            return arr[:, -1] * self.coef + self.bias
        return arr * self.coef + self.bias


def test_ml_vbt_alpha_top_k(synthetic_bars: pd.DataFrame) -> None:
    alpha = MLVbtAlpha(
        model=_DummyModel(coef=0.01, bias=-1.0),
        feature_columns=["close"],
        policy="top_k",
        top_k=2,
        rebalance=None,
        allow_short=True,
        use_size_in_signals=True,
    )
    universe = [Symbol.parse(v) for v in sorted(synthetic_bars["vt_symbol"].unique())]
    arr = alpha.generate_panel_signals(synthetic_bars, universe)
    assert isinstance(arr, SignalArrays)
    # At every rebalance row, at most 2 long entries fire.
    rows_with_entries = arr.entries.any(axis=1)
    assert rows_with_entries.any()
    for ts, has in rows_with_entries.items():
        if not has:
            continue
        assert arr.entries.loc[ts].sum() <= 2


def test_ml_vbt_alpha_threshold_policy(synthetic_bars: pd.DataFrame) -> None:
    alpha = MLVbtAlpha(
        model=_DummyModel(coef=0.0, bias=1.0),
        feature_columns=["close"],
        policy="threshold",
        threshold_long=0.0,
        threshold_short=-0.5,
        rebalance=None,
        allow_short=False,
        use_size_in_signals=False,
    )
    universe = [Symbol.parse(v) for v in sorted(synthetic_bars["vt_symbol"].unique())]
    arr = alpha.generate_panel_signals(synthetic_bars, universe)
    # Constant positive prediction => long across the board on the first row.
    first_row = arr.entries.iloc[0]
    assert first_row.all()


def test_ml_vbt_alpha_requires_a_model_source() -> None:
    with pytest.raises(ValueError):
        MLVbtAlpha(model=None, mlflow_uri=None).generate_panel_signals(
            pd.DataFrame(
                {
                    "timestamp": [pd.Timestamp("2024-01-01")],
                    "vt_symbol": ["AAPL.NASDAQ"],
                    "open": [1.0],
                    "high": [1.0],
                    "low": [1.0],
                    "close": [1.0],
                    "volume": [1.0],
                }
            ),
            universe=[Symbol.parse("AAPL.NASDAQ")],
        )
