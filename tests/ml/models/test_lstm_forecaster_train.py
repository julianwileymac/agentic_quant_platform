"""End-to-end smoke test: SPM LSTM forecaster training.

One of the three canonical platform smoke runs. Exercises:

- :class:`aqp.ml.models.spm._torch_base.TorchForecasterBase` training loop.
- :class:`aqp.ml.models.spm.forecasters.LSTMForecaster` via @register.
- :class:`aqp.ml.walk_forward.SimpleSliceDataset` adapter.

Requires PyTorch — skipped cleanly when not installed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch", reason="torch is required for SPM forecasters")

from aqp.ml.models.spm.forecasters import LSTMForecaster  # noqa: E402
from aqp.ml.models.spm._torch_base import TrainConfig  # noqa: E402
from aqp.ml.walk_forward import SimpleSliceDataset  # noqa: E402


def _make_dataset(synthetic_bars: pd.DataFrame) -> SimpleSliceDataset:
    """Single-symbol slice + next-bar log-return label."""
    sub = synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].copy()
    sub = sub.sort_values("timestamp").reset_index(drop=True).set_index("timestamp")
    sub["y"] = np.log(sub["close"].shift(-1) / sub["close"]).fillna(0.0)
    sub = sub[["y", "close", "volume"]].astype(float).dropna()
    return SimpleSliceDataset(frame=sub, label_col="y")


def test_lstm_forecaster_trains_two_epochs(synthetic_bars: pd.DataFrame) -> None:
    dataset = _make_dataset(synthetic_bars)
    cfg = TrainConfig(
        seq_len=10,
        hidden_size=16,
        num_layers=1,
        dropout=0.0,
        lr=1e-3,
        epochs=2,
        batch_size=32,
        device="cpu",
    )
    model = LSTMForecaster(config=cfg)
    fitted = model.fit(dataset)

    assert fitted is model, "fit() must return self per Model contract"
    assert fitted._fitted is True
    assert fitted.module is not None

    preds = fitted.predict(dataset, segment="test")
    assert isinstance(preds, pd.Series)
    assert len(preds) > 0, "prediction series must not be empty"
    assert np.all(np.isfinite(preds.to_numpy())), "predictions must be finite"

    # Predictions should sit in a sane numeric range (not exploding to inf or
    # NaN). Variance is allowed to be ~0 with only 2 epochs of training on
    # synthetic data — the network is small + briefly trained.
    assert preds.abs().max() < 1.0, "predictions should not explode out of range"


def test_lstm_forecaster_predict_without_fit_raises(synthetic_bars: pd.DataFrame) -> None:
    cfg = TrainConfig(epochs=0, device="cpu")
    model = LSTMForecaster(config=cfg)
    dataset = _make_dataset(synthetic_bars)
    with pytest.raises(RuntimeError, match="not fitted"):
        model.predict(dataset)
