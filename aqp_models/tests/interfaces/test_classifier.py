"""Smoke tests for the Classifier interface."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp_models.interfaces import Classifier


class _ProbModel:
    classes_ = ["bear", "neutral", "bull"]

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        n = len(frame)
        return np.tile(np.array([0.1, 0.3, 0.6]), (n, 1))


class _LogitsModel:
    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        n = len(frame)
        return np.tile(np.array([-1.0, 0.5, 2.0]), (n, 1))


def test_classifier_predict_proba() -> None:
    wrapper = Classifier(model=_ProbModel())
    frame = pd.DataFrame({"f0": [1.0]})
    out = wrapper.classify(frame)
    np.testing.assert_allclose(out.probabilities[-1], [0.1, 0.3, 0.6])
    assert out.predicted_class == "bull"
    assert out.metadata.extras["strategy"] == "predict_proba"


def test_classifier_softmax_fallback_with_logits() -> None:
    wrapper = Classifier(model=_LogitsModel(), classes=["low", "med", "high"])
    out = wrapper.classify(np.array([[0.0]]))
    # Logits [-1, 0.5, 2.0] -> argmax is "high".
    assert out.predicted_class == "high"
    np.testing.assert_almost_equal(out.probabilities.sum(axis=1), 1.0, decimal=6)
    assert out.metadata.extras["strategy"] == "softmax_from_predict"


def test_classifier_binary_predict_proba_emits_two_classes() -> None:
    class _BinaryProbModel:
        def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
            return np.array([[0.7]])  # single-col positive-class probability

    out = Classifier(model=_BinaryProbModel()).classify(pd.DataFrame({"f": [1.0]}))
    assert out.probabilities.shape == (1, 2)
    np.testing.assert_allclose(out.probabilities[0], [0.3, 0.7])
