"""Linear models — OLS / Ridge / Lasso / NNLS.

Reference: ``inspiration/qlib-main/qlib/contrib/model/linear.py``.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy


@register("LinearModel")
class LinearModel(Model):
    """Simple cross-sectional linear regression with pluggable regulariser.

    ``estimator`` is one of ``"ols"``, ``"ridge"``, ``"lasso"``, ``"nnls"``.
    """

    def __init__(
        self,
        estimator: str = "ridge",
        alpha: float = 1.0,
        fit_intercept: bool = True,
        **extra: Any,
    ) -> None:
        self.estimator = estimator
        self.alpha = float(alpha)
        self.fit_intercept = bool(fit_intercept)
        self.extra = extra
        self.coef_: np.ndarray | None = None
        self.intercept_: float = 0.0
        self.feature_names_: list[str] = []

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> LinearModel:
        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        sw = reweighter.reweight(X) if reweighter else None

        if self.estimator == "nnls":
            beta, _ = nnls(X, y)
            self.coef_ = beta
            self.intercept_ = 0.0
            return self

        if self.estimator in {"ridge", "lasso"}:
            from sklearn.linear_model import Lasso, Ridge

            est = Ridge if self.estimator == "ridge" else Lasso
            model = est(alpha=self.alpha, fit_intercept=self.fit_intercept, **self.extra)
            model.fit(X, y, sample_weight=sw)
            self.coef_ = np.asarray(model.coef_)
            self.intercept_ = float(getattr(model, "intercept_", 0.0))
            return self

        # OLS fallback via lstsq.
        if self.fit_intercept:
            X_ = np.hstack([np.ones((X.shape[0], 1)), X])
        else:
            X_ = X
        beta, *_ = np.linalg.lstsq(X_, y, rcond=None)
        if self.fit_intercept:
            self.intercept_ = float(beta[0])
            self.coef_ = np.asarray(beta[1:])
        else:
            self.intercept_ = 0.0
            self.coef_ = np.asarray(beta)
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.coef_ is None:
            raise RuntimeError("LinearModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = X @ self.coef_ + self.intercept_
        return predict_to_series(dataset, seg, np.asarray(preds))


__all__ = ["LinearModel"]
