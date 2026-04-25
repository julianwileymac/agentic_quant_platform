"""Tree-based models — LightGBM / XGBoost / CatBoost.

Each class implements :class:`aqp.ml.base.ModelFT` so it can ``fit`` a
``DatasetH`` and optionally ``finetune`` on a fresh segment. Reference:
``inspiration/qlib-main/qlib/contrib/model/{gbdt.py, xgboost.py, catboost_model.py}``.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import ModelFT, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy


@register("LGBModel")
class LGBModel(ModelFT):
    """LightGBM regressor wrapped in the Model contract."""

    def __init__(
        self,
        loss: str = "mse",
        num_leaves: int = 31,
        max_depth: int = -1,
        learning_rate: float = 0.05,
        n_estimators: int = 500,
        min_child_samples: int = 20,
        subsample: float = 1.0,
        colsample_bytree: float = 1.0,
        reg_alpha: float = 0.0,
        reg_lambda: float = 0.0,
        **extra: Any,
    ) -> None:
        self.params = {
            "objective": "regression" if loss == "mse" else loss,
            "num_leaves": int(num_leaves),
            "max_depth": int(max_depth),
            "learning_rate": float(learning_rate),
            "n_estimators": int(n_estimators),
            "min_child_samples": int(min_child_samples),
            "subsample": float(subsample),
            "colsample_bytree": float(colsample_bytree),
            "reg_alpha": float(reg_alpha),
            "reg_lambda": float(reg_lambda),
            "verbose": -1,
            **extra,
        }
        self.model: Any | None = None
        self.feature_names_: list[str] = []

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> LGBModel:
        import lightgbm as lgb

        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        sw = reweighter.reweight(X) if reweighter else None
        try:
            val_panel = prepare_panel(dataset, "valid")
            Xv, yv, _ = split_xy(val_panel)
            eval_set = [(Xv, yv)]
        except Exception:
            eval_set = None

        self.model = lgb.LGBMRegressor(**self.params)
        self.model.fit(X, y, sample_weight=sw, eval_set=eval_set)
        return self

    def finetune(self, dataset: Any) -> LGBModel:
        import lightgbm as lgb

        panel = prepare_panel(dataset, "train")
        X, y, _ = split_xy(panel)
        if self.model is None:
            return self.fit(dataset)
        self.model = lgb.LGBMRegressor(**self.params)
        self.model.fit(X, y, init_model=getattr(self, "_booster_path", None))
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model is None:
            raise RuntimeError("LGBModel.predict called before fit().")
        panel = prepare_panel(dataset, segment if isinstance(segment, str) else "test")
        X, _, _ = split_xy(panel)
        preds = self.model.predict(X)
        return predict_to_series(dataset, segment if isinstance(segment, str) else "test", preds)

    def feature_importance(self) -> dict[str, float]:
        if self.model is None:
            return {}
        try:
            importances = self.model.feature_importances_
        except AttributeError:
            return {}
        return dict(zip(self.feature_names_, (float(x) for x in importances), strict=False))


@register("XGBModel")
class XGBModel(ModelFT):
    """XGBoost regressor wrapped in the Model contract."""

    def __init__(
        self,
        n_estimators: int = 500,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        subsample: float = 1.0,
        colsample_bytree: float = 1.0,
        objective: str = "reg:squarederror",
        **extra: Any,
    ) -> None:
        self.params = {
            "n_estimators": int(n_estimators),
            "max_depth": int(max_depth),
            "learning_rate": float(learning_rate),
            "subsample": float(subsample),
            "colsample_bytree": float(colsample_bytree),
            "objective": objective,
            "n_jobs": -1,
            **extra,
        }
        self.model: Any | None = None
        self.feature_names_: list[str] = []

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> XGBModel:
        import xgboost as xgb

        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        sw = reweighter.reweight(X) if reweighter else None
        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(X, y, sample_weight=sw)
        return self

    def finetune(self, dataset: Any) -> XGBModel:
        return self.fit(dataset)

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model is None:
            raise RuntimeError("XGBModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = self.model.predict(X)
        return predict_to_series(dataset, seg, preds)


@register("CatBoostModel")
class CatBoostModel(ModelFT):
    """CatBoost regressor wrapped in the Model contract."""

    def __init__(
        self,
        iterations: int = 500,
        depth: int = 6,
        learning_rate: float = 0.05,
        loss_function: str = "RMSE",
        l2_leaf_reg: float = 3.0,
        **extra: Any,
    ) -> None:
        self.params = {
            "iterations": int(iterations),
            "depth": int(depth),
            "learning_rate": float(learning_rate),
            "loss_function": loss_function,
            "l2_leaf_reg": float(l2_leaf_reg),
            "verbose": 0,
            **extra,
        }
        self.model: Any | None = None

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> CatBoostModel:
        from catboost import CatBoostRegressor

        panel = prepare_panel(dataset, "train")
        X, y, _ = split_xy(panel)
        sw = reweighter.reweight(X) if reweighter else None
        self.model = CatBoostRegressor(**self.params)
        self.model.fit(X, y, sample_weight=sw)
        return self

    def finetune(self, dataset: Any) -> CatBoostModel:
        return self.fit(dataset)

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.model is None:
            raise RuntimeError("CatBoostModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = self.model.predict(X)
        return predict_to_series(dataset, seg, np.asarray(preds))


__all__ = ["CatBoostModel", "LGBModel", "XGBModel"]
