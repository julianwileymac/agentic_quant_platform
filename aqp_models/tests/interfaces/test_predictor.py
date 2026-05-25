"""Smoke tests for the Predictor interface."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp_models.interfaces import Predictor


class _StubModel:
    """Tiny model that returns the row-wise sum as the prediction."""

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.asarray(features.sum(axis=1).tolist(), dtype=float)


def test_predict_with_dataframe() -> None:
    model = _StubModel()
    predictor = Predictor(model=model, alias="stub")
    frame = pd.DataFrame({"f0": [1.0, 2.0], "f1": [3.0, 4.0]})
    result = predictor.predict(frame)
    assert result.values.shape == (2,)
    np.testing.assert_allclose(result.values, [4.0, 6.0])
    assert result.metadata is not None
    assert result.metadata.alias == "stub"


def test_predict_with_dict_payload() -> None:
    model = _StubModel()
    predictor = Predictor(model=model)
    result = predictor.predict({"f0": 10.0, "f1": -2.0})
    np.testing.assert_allclose(result.values, [8.0])


def test_predict_with_ndarray() -> None:
    model = _StubModel()
    predictor = Predictor(model=model)
    arr = np.array([[1.0, 1.0, 1.0]])
    result = predictor.predict(arr)
    np.testing.assert_allclose(result.values, [3.0])


def test_predict_to_json() -> None:
    model = _StubModel()
    predictor = Predictor(model=model)
    result = predictor.predict({"f0": 1.0, "f1": 2.0})
    payload = result.to_json()
    assert payload["values"] == [3.0]
    assert payload["shape"] == [1]
    assert payload["metadata"]["alias"]
