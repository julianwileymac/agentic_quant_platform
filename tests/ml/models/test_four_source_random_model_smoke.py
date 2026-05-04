"""Deterministic-random model smoke from the four-source cache."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.four_source_random import SELECTED_ASSETS, SEED, pick_assets

torch = pytest.importorskip("torch", reason="torch is required for four-source model smoke")


def _build_dataset(synthetic_bars: pd.DataFrame):
    from aqp.ml.walk_forward import SimpleSliceDataset

    sub = synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].copy()
    sub = sub.sort_values("timestamp").reset_index(drop=True).set_index("timestamp")
    sub["y"] = np.log(sub["close"].shift(-1) / sub["close"]).fillna(0.0)
    frame = sub[["y", "close", "volume"]].astype(float).dropna()
    return SimpleSliceDataset(frame=frame, label_col="y")


def test_model_selection_manifest_is_stable() -> None:
    assert pick_assets(SEED) == SELECTED_ASSETS
    assert SELECTED_ASSETS["model"] == "KerasMLPRegressor"


def test_selected_model_trains_and_predicts(synthetic_bars: pd.DataFrame) -> None:
    selected = SELECTED_ASSETS["model"]
    if selected != "KerasMLPRegressor":
        pytest.skip(f"Unsupported selected model: {selected}")

    from aqp.core.registry import get_metadata, list_by_kind
    from aqp.ml.models.sae.keras_mlp_regressor import KerasMLPRegressor

    model_cls = list_by_kind("model").get("KerasMLPRegressor")
    assert model_cls is KerasMLPRegressor
    meta = get_metadata(model_cls)
    assert meta.get("source") == "sae"
    assert meta.get("category") == "mlp"

    dataset = _build_dataset(synthetic_bars)
    model = KerasMLPRegressor(
        hidden_sizes=(4, 2),
        dropout=0.0,
        use_minmax=False,
        seq_len=10,
        epochs=1,
        batch_size=16,
        device="cpu",
    )
    fitted = model.fit(dataset)
    preds = fitted.predict(dataset, segment="test")

    assert isinstance(preds, pd.Series)
    assert len(preds) > 0
    assert np.all(np.isfinite(preds.to_numpy()))
