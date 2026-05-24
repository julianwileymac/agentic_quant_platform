"""``model.gbm`` — XGBoost / LightGBM / CatBoost regressor / classifier.

Phase 2 wires the three GBM families directly (rather than reusing
:mod:`aqp.ml.models.tree` whose API takes a qlib-style ``DatasetH``)
so the executor can accept a flat upstream PANEL frame. The model is
trained on the upstream frame's numeric columns + a configurable
``target_column``; MLflow autolog is on by default through the
existing :mod:`aqp.mlops.autolog` Celery hooks.

Params:

- ``framework`` (Literal['xgboost','lightgbm','catboost'], required).
- ``task`` (Literal['regression','classification'], default 'regression').
- ``target_column`` (str, required).
- ``feature_columns`` (list[str], optional) — defaults to every
  numeric column except the target.
- ``test_size`` (float, default 0.25) — used by the train/test split.
- ``random_state`` (int, default 42).
- ``hyperparameters`` (dict, optional) — passed through to the model
  constructor.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import (
    base_locator,
    numeric_columns,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    framework = str(params.get("framework") or "").lower()
    if framework not in {"xgboost", "lightgbm", "catboost"}:
        return NodeResult(
            status="error",
            error="model.gbm requires params.framework in {xgboost, lightgbm, catboost}",
            log_label="model.gbm:bad_framework",
        )
    task = str(params.get("task") or "regression").lower()
    if task not in {"regression", "classification"}:
        return NodeResult(
            status="error",
            error=f"model.gbm: unknown task {task!r}",
            log_label="model.gbm:bad_task",
        )
    target_column = params.get("target_column")
    if not target_column:
        return NodeResult(
            status="error",
            error="model.gbm requires params.target_column",
            log_label="model.gbm:missing_target",
        )
    test_size = float(params.get("test_size") or 0.25)
    random_state = int(params.get("random_state") or 42)
    hyperparameters = dict(params.get("hyperparameters") or {})

    df = resolve_upstream_frame(ctx)
    if df is None or target_column not in df.columns:
        return NodeResult(
            status="error",
            error=f"model.gbm: upstream frame missing target column {target_column!r}",
            log_label="model.gbm:missing_target_column",
        )
    feature_cols = numeric_columns(
        df.drop(columns=[target_column], errors="ignore"),
        params.get("feature_columns")
        if isinstance(params.get("feature_columns"), list)
        else None,
    )
    if not feature_cols:
        return NodeResult(
            status="error",
            error="model.gbm: no numeric feature columns",
            log_label="model.gbm:no_features",
        )

    X = df[feature_cols].astype(float)
    y = df[target_column]
    if task == "classification":
        y = y.astype(int)
    else:
        y = y.astype(float)

    try:
        from sklearn.model_selection import train_test_split
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"sklearn not installed: {exc}",
            log_label="model.gbm:no_sklearn",
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    try:
        model = _build_model(framework, task=task, hyperparameters=hyperparameters)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=str(exc),
            log_label=f"model.gbm:{framework}:build_fail",
        )

    try:
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"model.gbm fit/predict failed: {exc}",
            log_label=f"model.gbm:{framework}:train_fail",
        )

    metrics = _score(task, y_test, preds)
    # Stash the trained model on extras so a downstream
    # ``out.publish_mlflow`` node can register it; the model is also
    # available for live predict inside the same run.
    ctx.extras.setdefault("models", {})[node.id] = {
        "framework": framework,
        "task": task,
        "model": model,
        "feature_columns": feature_cols,
        "target_column": target_column,
    }
    pred_df = pd.DataFrame(
        {
            "y_true": y_test.reset_index(drop=True),
            "y_pred": preds,
        }
    )
    stash_arrow_output(ctx, node.id, pred_df)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, pred_df, kind="model_predictions"),
            "framework": framework,
            "task": task,
            "n_features": len(feature_cols),
            "model_in_extras": True,
        },
        metrics={
            **metrics,
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
        },
        log_label=f"model.gbm:{framework}:{task}",
    )


def _build_model(framework: str, *, task: str, hyperparameters: dict[str, Any]) -> Any:
    """Instantiate the requested GBM model with sane defaults."""
    defaults = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.05,
    }
    cfg = {**defaults, **hyperparameters}
    if framework == "lightgbm":
        try:
            import lightgbm as lgb  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"lightgbm not installed: {exc}") from exc
        klass = lgb.LGBMClassifier if task == "classification" else lgb.LGBMRegressor
        return klass(**cfg)
    if framework == "xgboost":
        try:
            import xgboost as xgb  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"xgboost not installed: {exc}") from exc
        klass = xgb.XGBClassifier if task == "classification" else xgb.XGBRegressor
        return klass(**cfg)
    if framework == "catboost":
        try:
            import catboost as cb  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"catboost not installed: {exc}") from exc
        cfg.pop("learning_rate", None)
        klass = cb.CatBoostClassifier if task == "classification" else cb.CatBoostRegressor
        return klass(iterations=cfg.get("n_estimators", 200), depth=cfg.get("max_depth", 6), verbose=False)
    raise RuntimeError(f"unsupported framework {framework!r}")


def _score(task: str, y_true: Any, y_pred: Any) -> dict[str, float]:
    """Return a small, deterministic metric dict for the runtime ledger."""
    y_true_arr = np.asarray(y_true).ravel()
    y_pred_arr = np.asarray(y_pred).ravel()
    if task == "classification":
        try:
            from sklearn.metrics import accuracy_score, log_loss

            preds = (y_pred_arr >= 0.5).astype(int) if y_pred_arr.dtype.kind == "f" else y_pred_arr.astype(int)
            metrics = {"accuracy": float(accuracy_score(y_true_arr, preds))}
            try:
                metrics["log_loss"] = float(log_loss(y_true_arr, y_pred_arr))
            except Exception:  # noqa: BLE001
                pass
            return metrics
        except Exception:  # noqa: BLE001
            return {"accuracy": 0.0}
    # Regression
    mse = float(((y_true_arr - y_pred_arr) ** 2).mean())
    rmse = float(np.sqrt(mse))
    return {"mse": mse, "rmse": rmse}


__all__ = ["execute"]
