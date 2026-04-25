"""Feature-importance routines (AFML ch. 8, ML4T ch. 13).

Three importance estimators useful across the platform:

* :func:`mdi_importance` — Mean Decrease in Impurity (scikit-learn
  ``feature_importances_`` averaged across trees with variance).
* :func:`mda_importance` — Mean Decrease in Accuracy via permutation
  under purged folds.
* :func:`single_feature_importance` — Out-of-fold score from training on
  *one feature at a time*. Useful for discovering orthogonal signals.

All three return a ``pd.DataFrame`` indexed by feature name with
``mean`` / ``std`` columns.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def mdi_importance(fit_model: Any, feature_names: list[str]) -> pd.DataFrame:
    """Mean Decrease in Impurity aggregated across trees.

    Works with any sklearn-compatible forest (``feature_importances_``
    per tree in ``estimators_``). For non-forest models that only expose
    the global ``feature_importances_`` the std is set to 0.
    """
    importances_per_tree = getattr(fit_model, "estimators_", None)
    if importances_per_tree:
        rows = [tree.feature_importances_ for tree in importances_per_tree]
        arr = np.asarray(rows)
        mean = arr.mean(axis=0)
        std = arr.std(axis=0) * (arr.shape[0] ** -0.5)
    else:
        importances = getattr(fit_model, "feature_importances_", None)
        if importances is None:
            raise ValueError("fit_model lacks feature_importances_")
        mean = np.asarray(importances)
        std = np.zeros_like(mean)
    mean = mean / mean.sum() if mean.sum() else mean
    return pd.DataFrame({"mean": mean, "std": std}, index=feature_names).sort_values(
        "mean", ascending=False
    )


def _score(y_true: np.ndarray, y_pred: np.ndarray, scoring: str) -> float:
    if scoring == "neg_log_loss":
        from sklearn.metrics import log_loss

        y_pred = np.clip(y_pred, 1e-8, 1 - 1e-8)
        return -log_loss(y_true, y_pred)
    if scoring == "accuracy":
        from sklearn.metrics import accuracy_score

        return float(accuracy_score(y_true, y_pred.round()))
    if scoring == "r2":
        from sklearn.metrics import r2_score

        return float(r2_score(y_true, y_pred))
    raise ValueError(f"Unknown scoring {scoring!r}")


def mda_importance(
    fit_model_factory: Callable[[], Any],
    X: pd.DataFrame,
    y: pd.Series,
    splitter: Any,
    scoring: str = "neg_log_loss",
    sample_weight: pd.Series | None = None,
    predict_proba: bool = True,
    seed: int = 42,
) -> pd.DataFrame:
    """Mean Decrease in Accuracy via permutation on purged folds.

    For each fold:

    1. Fit a fresh model on the training rows.
    2. Score on test rows.
    3. For each feature: permute that column within the test rows and
       score again. The delta is the feature's importance contribution.
    """
    rng = np.random.default_rng(seed)
    feature_names = list(X.columns)
    scores_full = []
    scores_perm: dict[str, list[float]] = {c: [] for c in feature_names}

    for train_idx, test_idx in splitter.split(X):
        X_tr = X.iloc[train_idx]
        y_tr = y.iloc[train_idx]
        X_te = X.iloc[test_idx]
        y_te = y.iloc[test_idx]
        w_tr = sample_weight.iloc[train_idx].values if sample_weight is not None else None
        try:
            model = fit_model_factory()
            if w_tr is not None:
                model.fit(X_tr, y_tr, sample_weight=w_tr)
            else:
                model.fit(X_tr, y_tr)
        except Exception:
            logger.exception("mda fit failed in fold")
            continue
        if predict_proba and hasattr(model, "predict_proba"):
            y_pred = model.predict_proba(X_te)[:, 1]
        else:
            y_pred = model.predict(X_te)
        scores_full.append(_score(y_te.values, np.asarray(y_pred), scoring))

        for col in feature_names:
            Xp = X_te.copy()
            perm = rng.permutation(Xp[col].values)
            Xp[col] = perm
            if predict_proba and hasattr(model, "predict_proba"):
                yp = model.predict_proba(Xp)[:, 1]
            else:
                yp = model.predict(Xp)
            scores_perm[col].append(_score(y_te.values, np.asarray(yp), scoring))

    baseline = np.mean(scores_full) if scores_full else 0.0
    records: list[dict[str, float]] = []
    for col in feature_names:
        vals = scores_perm[col]
        if not vals:
            records.append({"feature": col, "mean": 0.0, "std": 0.0})
            continue
        deltas = np.asarray(vals) - baseline
        records.append(
            {
                "feature": col,
                "mean": float(-deltas.mean()),  # importance = drop from baseline
                "std": float(deltas.std() * (len(deltas) ** -0.5)),
            }
        )
    out = pd.DataFrame(records).set_index("feature").sort_values("mean", ascending=False)
    return out


def single_feature_importance(
    fit_model_factory: Callable[[], Any],
    X: pd.DataFrame,
    y: pd.Series,
    splitter: Any,
    scoring: str = "neg_log_loss",
    predict_proba: bool = True,
) -> pd.DataFrame:
    """Score of a model trained on *one feature at a time*."""
    feature_names = list(X.columns)
    records: list[dict[str, float]] = []
    for col in feature_names:
        fold_scores: list[float] = []
        for train_idx, test_idx in splitter.split(X):
            try:
                model = fit_model_factory()
                X_tr = X.iloc[train_idx][[col]]
                X_te = X.iloc[test_idx][[col]]
                model.fit(X_tr, y.iloc[train_idx])
                if predict_proba and hasattr(model, "predict_proba"):
                    pred = model.predict_proba(X_te)[:, 1]
                else:
                    pred = model.predict(X_te)
                fold_scores.append(_score(y.iloc[test_idx].values, np.asarray(pred), scoring))
            except Exception:
                continue
        records.append(
            {
                "feature": col,
                "mean": float(np.mean(fold_scores) if fold_scores else 0.0),
                "std": float(np.std(fold_scores) if fold_scores else 0.0),
            }
        )
    return pd.DataFrame(records).set_index("feature").sort_values("mean", ascending=False)


__all__ = [
    "mda_importance",
    "mdi_importance",
    "single_feature_importance",
]
