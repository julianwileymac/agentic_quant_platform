"""Ridge "virtue of complexity" forecaster (Kelly et al.).

Random non-linear features (random projections + ReLU) lifted into a
high-dimensional space, then a single Ridge regression. Captures the
Kelly et al. result that complexity helps generalization with sufficient
shrinkage.

Source: ``inspiration/notebooks-master/the_virtue_of_complexity_everywhere.ipynb``
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter

logger = logging.getLogger(__name__)


@register("RidgeVoCForecaster", source="notebooks", category="bayesian", kind="model")
class RidgeVoCForecaster(Model):
    """Ridge-on-random-features forecaster.

    Parameters:
        p_features: number of random projections.
        alpha: Ridge regularisation strength.
        random_state: reproducibility seed.
    """

    def __init__(self, p_features: int = 256, alpha: float = 1.0, random_state: int = 42) -> None:
        self.p_features = int(p_features)
        self.alpha = float(alpha)
        self.random_state = int(random_state)
        self._W: np.ndarray | None = None
        self._b: np.ndarray | None = None
        self._model = None

    def _lift(self, X: np.ndarray) -> np.ndarray:
        rng = np.random.default_rng(self.random_state)
        if self._W is None or self._W.shape[0] != X.shape[1]:
            self._W = rng.standard_normal((X.shape[1], self.p_features))
            self._b = rng.standard_normal(self.p_features)
        proj = X @ self._W + self._b
        return np.maximum(proj, 0.0)  # ReLU

    def fit(self, dataset, reweighter: Reweighter | None = None):
        try:
            from sklearn.linear_model import Ridge
        except ImportError as exc:  # pragma: no cover
            raise ImportError("scikit-learn required for RidgeVoCForecaster") from exc
        X, y = self._extract(dataset)
        if len(X) == 0:
            return self
        Z = self._lift(X)
        self._model = Ridge(alpha=self.alpha)
        self._model.fit(Z, y)
        return self

    def predict(self, dataset, segment="test") -> pd.Series:
        if self._model is None:
            raise RuntimeError("Call fit() first.")
        X, _ = self._extract(dataset)
        if len(X) == 0:
            return pd.Series(dtype=float)
        Z = self._lift(X)
        preds = self._model.predict(Z)
        index = self._extract_index(dataset)
        if index is not None and len(index) >= len(preds):
            return pd.Series(preds, index=index[-len(preds):])
        return pd.Series(preds)

    @staticmethod
    def _extract(dataset: Any) -> tuple[np.ndarray, np.ndarray]:
        if hasattr(dataset, "to_arrays"):
            return dataset.to_arrays()
        if isinstance(dataset, pd.DataFrame):
            label_col = "y" if "y" in dataset.columns else dataset.columns[-1]
            features = dataset.drop(columns=[label_col]).to_numpy(dtype=float)
            labels = dataset[label_col].to_numpy(dtype=float)
            return features, labels
        if isinstance(dataset, tuple) and len(dataset) == 2:
            return np.asarray(dataset[0], dtype=float), np.asarray(dataset[1], dtype=float)
        arr = np.asarray(dataset, dtype=float)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            return arr[:, :-1], arr[:, -1]
        return arr.reshape(-1, 1), arr

    @staticmethod
    def _extract_index(dataset: Any) -> pd.Index | None:
        return getattr(dataset, "index", None)


__all__ = ["RidgeVoCForecaster"]
