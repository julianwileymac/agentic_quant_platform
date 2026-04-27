"""High-frequency LightGBM model — qlib ``highfreq_gdbt_model.py``.

LightGBM tuned for intraday minute-bar features. The model is a thin
specialisation of :class:`aqp.ml.models.tree.LGBModel` with hyper-
parameters biased toward sparser leaves and higher row sampling for
the typically-large intraday panels.

Optionally accepts a list of "highfreq feature columns" that the panel
loader has already produced (e.g. minute-bar OBV, intraday VWAP, etc.)
and ensures the model is restricted to those columns at fit time when
``feature_subset`` is provided.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.registry import register
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy
from aqp.ml.models.tree import LGBModel


@register("HighFreqGBDT")
class HighFreqGBDT(LGBModel):
    """LightGBM tuned for intraday minute-bar feature panels."""

    def __init__(
        self,
        num_leaves: int = 63,
        learning_rate: float = 0.03,
        n_estimators: int = 1500,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        min_child_samples: int = 50,
        feature_subset: list[str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(
            num_leaves=num_leaves,
            learning_rate=learning_rate,
            n_estimators=n_estimators,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            min_child_samples=min_child_samples,
            **extra,
        )
        self.feature_subset = list(feature_subset) if feature_subset else None

    def _maybe_subset(self, panel: pd.DataFrame) -> pd.DataFrame:
        if not self.feature_subset:
            return panel
        keep = [c for c in panel.columns if c in self.feature_subset or c in {"label", "y"}]
        if not keep:
            return panel
        return panel[keep]

    def fit(self, dataset: Any, reweighter: Any | None = None) -> "HighFreqGBDT":
        import lightgbm as lgb

        panel = prepare_panel(dataset, "train")
        panel = self._maybe_subset(panel)
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        sw = reweighter.reweight(X) if reweighter else None
        try:
            val = prepare_panel(dataset, "valid")
            val = self._maybe_subset(val)
            Xv, yv, _ = split_xy(val)
            eval_set = [(Xv, yv)]
        except Exception:
            eval_set = None

        self.model = lgb.LGBMRegressor(**self.params)
        self.model.fit(X, y, sample_weight=sw, eval_set=eval_set)
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model is None:
            raise RuntimeError("HighFreqGBDT.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = self._maybe_subset(prepare_panel(dataset, seg))
        X, _, _ = split_xy(panel)
        preds = self.model.predict(X)
        return predict_to_series(dataset, seg, preds)


__all__ = ["HighFreqGBDT"]
