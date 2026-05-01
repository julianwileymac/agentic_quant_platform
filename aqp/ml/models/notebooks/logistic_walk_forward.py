"""Logistic walk-forward classifier port from akquant.

Source: ``inspiration/akquant-main/examples/10_ml_walk_forward.py`` and
``pb_mock.py``. Trains a sklearn ``LogisticRegression`` (or full
``Pipeline`` with ``StandardScaler``) on lagged features and predicts
next-bar direction.

Despite living under ``aqp/ml/models/notebooks/`` (the canonical home
for notebook ports), the source is the akquant example. Kept here for
proximity to other walk-forward ML models.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter

logger = logging.getLogger(__name__)


@register("LogisticWalkForwardClassifier", source="akquant", category="classifier", kind="model")
class LogisticWalkForwardClassifier(Model):
    """Logistic regression on lagged returns; pairs with WalkForwardTrainer."""

    def __init__(self, n_lags: int = 5, use_scaler: bool = True, C: float = 1.0) -> None:
        self.n_lags = n_lags
        self.use_scaler = use_scaler
        self.C = C
        self._pipeline = None

    def fit(self, dataset, reweighter: Reweighter | None = None):
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
        except ImportError as exc:  # pragma: no cover
            raise ImportError("scikit-learn required for LogisticWalkForwardClassifier") from exc

        X, y = self._extract(dataset)
        if len(X) == 0:
            return self
        steps = []
        if self.use_scaler:
            steps.append(("scaler", StandardScaler()))
        steps.append(("clf", LogisticRegression(C=self.C, max_iter=1000)))
        self._pipeline = Pipeline(steps)
        # binarize labels
        y_bin = (y > 0).astype(int)
        self._pipeline.fit(X, y_bin)
        return self

    def predict(self, dataset, segment="test") -> pd.Series:
        if self._pipeline is None:
            raise RuntimeError("Call fit() first.")
        X, _ = self._extract(dataset)
        if len(X) == 0:
            return pd.Series(dtype=float)
        proba = self._pipeline.predict_proba(X)[:, 1]
        index = getattr(dataset, "index", None)
        if index is not None and len(index) >= len(proba):
            return pd.Series(proba, index=index[-len(proba):])
        return pd.Series(proba)

    def _extract(self, dataset: Any) -> tuple[np.ndarray, np.ndarray]:
        if hasattr(dataset, "to_arrays"):
            return dataset.to_arrays()
        if isinstance(dataset, pd.DataFrame):
            label_col = "y" if "y" in dataset.columns else dataset.columns[-1]
            features = dataset.drop(columns=[label_col]).to_numpy(dtype=float)
            labels = dataset[label_col].to_numpy(dtype=float)
            return features, labels
        return np.asarray(dataset, dtype=float).reshape(-1, 1), np.zeros(len(dataset))


__all__ = ["LogisticWalkForwardClassifier"]
