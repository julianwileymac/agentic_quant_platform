"""Tests for the ML-prediction-as-indicator adapter."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_bars() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-01", "2024-02-15")
    rows = []
    for sym in ("AAA.NASDAQ", "BBB.NASDAQ"):
        prices = 100 + np.cumsum(rng.normal(0, 1, size=len(dates)))
        for ts, px in zip(dates, prices, strict=True):
            rows.append(
                {
                    "timestamp": ts,
                    "vt_symbol": sym,
                    "open": float(px),
                    "high": float(px + 1),
                    "low": float(px - 1),
                    "close": float(px),
                    "volume": 1_000_000.0,
                }
            )
    return pd.DataFrame(rows)


def test_is_model_pred_spec() -> None:
    from aqp.data.model_prediction import is_model_pred_spec

    assert is_model_pred_spec("ModelPred")
    assert is_model_pred_spec("modelpred")
    assert is_model_pred_spec("model_pred")
    assert not is_model_pred_spec("SMA")
    assert not is_model_pred_spec("")


def test_apply_model_predictions_adds_nan_when_no_model(
    sample_bars: pd.DataFrame,
) -> None:
    from aqp.data.model_prediction import apply_model_predictions

    out = apply_model_predictions(
        sample_bars,
        specs=[("ModelPred", {"deployment_id": "does-not-exist", "column_name": "model_pred_test"})],
    )
    assert "model_pred_test" in out.columns
    # All NaN because the deployment can't be resolved.
    assert out["model_pred_test"].isna().all()


def test_indicator_zoo_passes_through_model_specs(sample_bars: pd.DataFrame) -> None:
    from aqp.data.indicators_zoo import IndicatorZoo

    out = IndicatorZoo().transform(
        sample_bars,
        indicators=["SMA:5", "ModelPred:deployment_id=fake-id,column_name=mp1"],
    )
    assert "sma_5" in out.columns
    assert "mp1" in out.columns
    # Existing rows preserved.
    assert len(out) == len(sample_bars)


def test_feature_engineer_extra_indicators(sample_bars: pd.DataFrame) -> None:
    from aqp.data.feature_engineer import FeatureEngineer

    fe = FeatureEngineer(
        indicators=["sma_20"],
        extra_indicators=["RSI:7", "ModelPred:deployment_id=fake,column_name=mp_extra"],
    )
    out = fe.transform(sample_bars)
    assert "sma_20" in out.columns
    assert "rsi_7" in out.columns
    assert "mp_extra" in out.columns
