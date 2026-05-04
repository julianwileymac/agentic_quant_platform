"""scikit-learn model adapters for the native ``aqp.ml`` contract."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import build_from_config, register
from aqp.ml.base import Model, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel, split_xy


def _make_regressor(name: str, params: dict[str, Any]) -> Any:
    try:
        if name == "ridge":
            from sklearn.linear_model import Ridge

            return Ridge(**params)
        if name == "lasso":
            from sklearn.linear_model import Lasso

            return Lasso(**params)
        if name == "elastic_net":
            from sklearn.linear_model import ElasticNet

            return ElasticNet(**params)
        if name == "random_forest":
            from sklearn.ensemble import RandomForestRegressor

            return RandomForestRegressor(**params)
        if name == "gradient_boosting":
            from sklearn.ensemble import GradientBoostingRegressor

            return GradientBoostingRegressor(**params)
        if name == "hist_gradient_boosting":
            from sklearn.ensemble import HistGradientBoostingRegressor

            return HistGradientBoostingRegressor(**params)
        if name == "svr":
            from sklearn.svm import SVR

            return SVR(**params)
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("scikit-learn is not installed. Install the `ml` extra.") from exc
    raise ValueError(f"Unknown sklearn regressor {name!r}")


def _make_classifier(name: str, params: dict[str, Any]) -> Any:
    try:
        if name == "logistic_regression":
            from sklearn.linear_model import LogisticRegression

            return LogisticRegression(**params)
        if name == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            return RandomForestClassifier(**params)
        if name == "gradient_boosting":
            from sklearn.ensemble import GradientBoostingClassifier

            return GradientBoostingClassifier(**params)
        if name == "svc":
            from sklearn.svm import SVC

            return SVC(probability=True, **params)
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("scikit-learn is not installed. Install the `ml` extra.") from exc
    raise ValueError(f"Unknown sklearn classifier {name!r}")


@register("SklearnRegressorModel")
class SklearnRegressorModel(Model):
    """Wrap any sklearn-style regressor in AQP's DatasetH model contract."""

    def __init__(
        self,
        estimator: str = "ridge",
        estimator_cfg: dict[str, Any] | None = None,
        estimator_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.estimator_name = str(estimator)
        self.estimator_cfg = dict(estimator_cfg or {})
        self.estimator_kwargs = dict(estimator_kwargs or {})
        self.estimator_: Any | None = None
        self.feature_names_: list[str] = []

    def _build_estimator(self) -> Any:
        if self.estimator_cfg:
            return build_from_config(self.estimator_cfg)
        return _make_regressor(self.estimator_name, self.estimator_kwargs)

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> SklearnRegressorModel:
        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        sw = reweighter.reweight(X) if reweighter else None
        self.estimator_ = self._build_estimator()
        try:
            self.estimator_.fit(X, y, sample_weight=sw)
        except TypeError:
            self.estimator_.fit(X, y)
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.estimator_ is None:
            raise RuntimeError("SklearnRegressorModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        preds = np.asarray(self.estimator_.predict(X), dtype=float).reshape(-1)
        return predict_to_series(dataset, seg, preds)

    def feature_importance(self) -> dict[str, float]:
        if self.estimator_ is None:
            return {}
        values = getattr(self.estimator_, "feature_importances_", None)
        if values is None:
            values = getattr(self.estimator_, "coef_", None)
        if values is None:
            return {}
        arr = np.asarray(values, dtype=float).reshape(-1)
        return dict(zip(self.feature_names_, (float(v) for v in arr), strict=False))


@register("SklearnClassifierModel")
class SklearnClassifierModel(Model):
    """Binary classifier adapter that returns class-1 probability as alpha score."""

    def __init__(
        self,
        estimator: str = "logistic_regression",
        estimator_cfg: dict[str, Any] | None = None,
        estimator_kwargs: dict[str, Any] | None = None,
        positive_threshold: float = 0.0,
    ) -> None:
        self.estimator_name = str(estimator)
        self.estimator_cfg = dict(estimator_cfg or {})
        self.estimator_kwargs = dict(estimator_kwargs or {})
        self.positive_threshold = float(positive_threshold)
        self.estimator_: Any | None = None
        self.feature_names_: list[str] = []

    def _build_estimator(self) -> Any:
        if self.estimator_cfg:
            return build_from_config(self.estimator_cfg)
        return _make_classifier(self.estimator_name, self.estimator_kwargs)

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> SklearnClassifierModel:
        panel = prepare_panel(dataset, "train")
        X, y, features = split_xy(panel)
        self.feature_names_ = features
        labels = (np.asarray(y, dtype=float) > self.positive_threshold).astype(int)
        sw = reweighter.reweight(X) if reweighter else None
        self.estimator_ = self._build_estimator()
        try:
            self.estimator_.fit(X, labels, sample_weight=sw)
        except TypeError:
            self.estimator_.fit(X, labels)
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if self.estimator_ is None:
            raise RuntimeError("SklearnClassifierModel.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, _ = split_xy(panel)
        if hasattr(self.estimator_, "predict_proba"):
            proba = np.asarray(self.estimator_.predict_proba(X), dtype=float)
            preds = proba[:, 1] if proba.ndim == 2 and proba.shape[1] > 1 else proba.reshape(-1)
        elif hasattr(self.estimator_, "decision_function"):
            raw = np.asarray(self.estimator_.decision_function(X), dtype=float).reshape(-1)
            preds = 1.0 / (1.0 + np.exp(-raw))
        else:
            preds = np.asarray(self.estimator_.predict(X), dtype=float).reshape(-1)
        return predict_to_series(dataset, seg, preds)


@register("SklearnPipelineModel")
class SklearnPipelineModel(SklearnRegressorModel):
    """Build a sklearn ``Pipeline`` from configured steps.

    ``steps`` accepts ``[{name, estimator_cfg}]`` entries where
    ``estimator_cfg`` follows the platform's ``class/module_path/kwargs`` shape.
    """

    def __init__(
        self,
        steps: list[dict[str, Any]],
    ) -> None:
        super().__init__(estimator="pipeline")
        self.steps = list(steps)

    def _build_estimator(self) -> Any:
        try:
            from sklearn.pipeline import Pipeline
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError("scikit-learn is not installed. Install the `ml` extra.") from exc
        built_steps = []
        for idx, step in enumerate(self.steps):
            name = str(step.get("name") or f"step_{idx}")
            cfg = step.get("estimator_cfg") or step.get("cfg")
            if not isinstance(cfg, dict):
                raise ValueError(f"Pipeline step {name!r} needs estimator_cfg")
            built_steps.append((name, build_from_config(cfg)))
        return Pipeline(built_steps)


@register("SklearnStackingModel", kind="model")
class SklearnStackingModel(SklearnRegressorModel):
    """Stacking ensemble of heterogeneous sklearn estimators.

    ``estimators`` is a list of ``{name, estimator_cfg}`` entries (each
    following the platform ``{class, module_path, kwargs}`` shape). The
    stack's final estimator defaults to a ``Ridge`` if not given.
    """

    def __init__(
        self,
        estimators: list[dict[str, Any]],
        final_estimator_cfg: dict[str, Any] | None = None,
        passthrough: bool = False,
        cv: int = 5,
    ) -> None:
        super().__init__(estimator="stacking")
        self.estimators = list(estimators)
        self.final_estimator_cfg = dict(final_estimator_cfg or {})
        self.passthrough = bool(passthrough)
        self.cv = int(cv)

    def _build_estimator(self) -> Any:
        try:
            from sklearn.ensemble import StackingRegressor
            from sklearn.linear_model import Ridge
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "scikit-learn is not installed. Install the `ml` extra."
            ) from exc
        built = []
        for idx, est in enumerate(self.estimators):
            name = str(est.get("name") or f"est_{idx}")
            cfg = est.get("estimator_cfg") or est.get("cfg")
            if not isinstance(cfg, dict):
                raise ValueError(f"Stacking estimator {name!r} needs estimator_cfg")
            built.append((name, build_from_config(cfg)))
        final_estimator = (
            build_from_config(self.final_estimator_cfg)
            if self.final_estimator_cfg
            else Ridge()
        )
        return StackingRegressor(
            estimators=built,
            final_estimator=final_estimator,
            passthrough=self.passthrough,
            cv=self.cv,
        )


@register("SklearnAutoPipelineModel", kind="model")
class SklearnAutoPipelineModel(SklearnRegressorModel):
    """Auto-build a sklearn Pipeline with imputer + scaler + estimator.

    Convenience wrapper for the most common preprocessing + model stack
    where users do not want to spell out a full ``SklearnPipelineModel``.
    """

    def __init__(
        self,
        estimator: str = "ridge",
        estimator_kwargs: dict[str, Any] | None = None,
        scaler: str = "standard",
        imputer_strategy: str = "median",
    ) -> None:
        super().__init__(
            estimator=estimator, estimator_kwargs=estimator_kwargs
        )
        self.scaler = str(scaler).lower()
        self.imputer_strategy = str(imputer_strategy)

    def _build_estimator(self) -> Any:
        try:
            from sklearn.impute import SimpleImputer
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import (
                MinMaxScaler,
                RobustScaler,
                StandardScaler,
            )
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "scikit-learn is not installed. Install the `ml` extra."
            ) from exc
        scalers = {
            "standard": StandardScaler,
            "robust": RobustScaler,
            "minmax": MinMaxScaler,
        }
        scaler_cls = scalers.get(self.scaler, StandardScaler)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy=self.imputer_strategy)),
                ("scale", scaler_cls()),
                ("model", _make_regressor(self.estimator_name, self.estimator_kwargs)),
            ]
        )


__all__ = [
    "SklearnAutoPipelineModel",
    "SklearnClassifierModel",
    "SklearnPipelineModel",
    "SklearnRegressorModel",
    "SklearnStackingModel",
]
