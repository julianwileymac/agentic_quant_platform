"""Quick linear-model helpers for notebooks.

The "quick" namespace is deliberately import-light and never raises on
empty data — it returns a dataclass with reasonable defaults so a user
can chain calls without try/except.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class QuickRegressionResult:
    """Outcome of a quick linear / ridge / elasticnet fit."""

    estimator: str
    score: float = 0.0
    rmse: float = 0.0
    mae: float = 0.0
    coefficients: dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0
    n_train: int = 0
    n_features: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def _prepare(features: pd.DataFrame, target: pd.Series) -> tuple[np.ndarray, np.ndarray, list[str]]:
    df = features.copy()
    if isinstance(df, pd.Series):
        df = df.to_frame()
    df = df.replace([np.inf, -np.inf], np.nan)
    target = pd.Series(target).astype(float).replace([np.inf, -np.inf], np.nan)
    joined = pd.concat([df, target.rename("__target__")], axis=1).dropna()
    if joined.empty:
        return np.zeros((0, df.shape[1])), np.zeros(0), list(df.columns)
    y = joined["__target__"].to_numpy(dtype=float)
    X = joined.drop(columns="__target__").to_numpy(dtype=float)
    return X, y, [str(c) for c in df.columns]


def _materialize(
    estimator: Any,
    X: np.ndarray,
    y: np.ndarray,
    features: list[str],
    name: str,
) -> QuickRegressionResult:
    if X.size == 0:
        return QuickRegressionResult(
            estimator=name,
            n_train=0,
            n_features=len(features),
            notes="No usable rows after NaN drop",
        )
    estimator.fit(X, y)
    score = float(estimator.score(X, y))
    pred = np.asarray(estimator.predict(X), dtype=float).reshape(-1)
    err = pred - y
    coefs = getattr(estimator, "coef_", None)
    intercept = getattr(estimator, "intercept_", 0.0)
    coef_map = (
        {feat: float(coef) for feat, coef in zip(features, np.asarray(coefs).reshape(-1), strict=False)}
        if coefs is not None
        else {}
    )
    return QuickRegressionResult(
        estimator=name,
        score=score,
        rmse=float(np.sqrt(np.mean(np.square(err)))),
        mae=float(np.mean(np.abs(err))),
        coefficients=coef_map,
        intercept=float(intercept) if np.isscalar(intercept) else float(np.asarray(intercept).reshape(-1)[0]),
        n_train=int(len(y)),
        n_features=int(X.shape[1]),
    )


def quick_ridge(
    features: pd.DataFrame, target: pd.Series, *, alpha: float = 1.0
) -> QuickRegressionResult:
    """Fit a Ridge regression in two lines."""
    try:
        from sklearn.linear_model import Ridge
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install the `ml` extra."
        ) from exc
    X, y, feats = _prepare(features, target)
    return _materialize(Ridge(alpha=alpha), X, y, feats, "ridge")


def quick_elasticnet(
    features: pd.DataFrame,
    target: pd.Series,
    *,
    alpha: float = 1.0,
    l1_ratio: float = 0.5,
) -> QuickRegressionResult:
    """Fit an ElasticNet regression in two lines."""
    try:
        from sklearn.linear_model import ElasticNet
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install the `ml` extra."
        ) from exc
    X, y, feats = _prepare(features, target)
    return _materialize(
        ElasticNet(alpha=alpha, l1_ratio=l1_ratio), X, y, feats, "elasticnet"
    )


def quick_panel_fixed_effects(
    panel: pd.DataFrame,
    *,
    target_col: str,
    entity_col: str = "vt_symbol",
    time_col: str = "timestamp",
    feature_cols: list[str] | None = None,
) -> QuickRegressionResult:
    """Fit a within-entity (fixed-effects) regression on a panel.

    Demeans both target and features by entity, then runs OLS on the
    demeaned values. Useful for sanity-checking whether a relationship
    holds within each instrument or only on the cross-section.
    """
    try:
        from sklearn.linear_model import LinearRegression
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install the `ml` extra."
        ) from exc
    if entity_col not in panel.columns or target_col not in panel.columns:
        raise ValueError(
            f"panel must contain {entity_col!r} and {target_col!r}"
        )
    feature_cols = list(
        feature_cols
        or [c for c in panel.columns if c not in {entity_col, time_col, target_col}]
    )
    df = panel[[entity_col, target_col, *feature_cols]].copy()
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    if df.empty:
        return QuickRegressionResult(
            estimator="panel_fixed_effects",
            n_train=0,
            n_features=len(feature_cols),
            notes="No usable rows after NaN drop",
        )
    grouped = df.groupby(entity_col)
    demeaned = df.copy()
    for col in [target_col, *feature_cols]:
        demeaned[col] = df[col] - grouped[col].transform("mean")
    X = demeaned[feature_cols].to_numpy(dtype=float)
    y = demeaned[target_col].to_numpy(dtype=float)
    return _materialize(LinearRegression(), X, y, feature_cols, "panel_fixed_effects")


__all__ = [
    "QuickRegressionResult",
    "quick_elasticnet",
    "quick_panel_fixed_effects",
    "quick_ridge",
]
