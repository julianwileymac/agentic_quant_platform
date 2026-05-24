"""``model.sklearn`` — train a registered sklearn estimator.

Phase 3 minimum surface: fits one of ``LinearRegression`` /
``LogisticRegression`` / ``RandomForestRegressor`` /
``RandomForestClassifier`` on the upstream features + target frame.
Heavier models live behind the ``model.gbm`` / ``model.torch`` /
``model.rl`` nodes which all dispatch through MLflow autolog.

Params:

- ``estimator`` (str, required) — one of ``linreg`` / ``logreg`` /
  ``rf_regressor`` / ``rf_classifier``.
- ``target_column`` (str, required).
- ``feature_columns`` (list[str] | None) — defaults to every numeric
  column except the target.
- ``test_size`` (float, default 0.2) — used for the simple in-process
  holdout score; the full sweep + CPCV path runs through the
  evaluation compiler.
"""
from __future__ import annotations

import numpy as np

from aqp.lab.executors._helpers import (
    base_locator,
    numeric_columns,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    estimator = str(params.get("estimator") or "linreg").lower()
    target_col = str(params.get("target_column") or "")
    feature_cols = params.get("feature_columns")
    test_size = float(params.get("test_size") or 0.2)

    if not target_col:
        return NodeResult(status="error", error="model.sklearn requires 'target_column'")

    df = resolve_upstream_frame(ctx)
    if df is None or target_col not in df.columns:
        return NodeResult(
            status="error",
            error=f"model.sklearn needs upstream frame with '{target_col}' column",
        )

    cols = numeric_columns(df, feature_cols)
    cols = [c for c in cols if c != target_col]
    if not cols:
        return NodeResult(status="error", error="model.sklearn found no feature columns")

    X = df[cols].to_numpy(dtype=float)
    y = df[target_col].to_numpy()
    n = len(X)
    split = max(1, int(n * (1.0 - test_size)))
    X_tr, X_te = X[:split], X[split:]
    y_tr, y_te = y[:split], y[split:]

    try:
        if estimator == "linreg":
            from sklearn.linear_model import LinearRegression  # type: ignore[import-not-found]

            model = LinearRegression()
        elif estimator == "logreg":
            from sklearn.linear_model import LogisticRegression  # type: ignore[import-not-found]

            model = LogisticRegression(max_iter=1000)
        elif estimator == "rf_regressor":
            from sklearn.ensemble import RandomForestRegressor  # type: ignore[import-not-found]

            model = RandomForestRegressor(
                n_estimators=int(params.get("n_estimators") or 100),
                random_state=int(params.get("random_state") or 42),
            )
        elif estimator == "rf_classifier":
            from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-not-found]

            model = RandomForestClassifier(
                n_estimators=int(params.get("n_estimators") or 100),
                random_state=int(params.get("random_state") or 42),
            )
        else:
            return NodeResult(
                status="error",
                error=f"model.sklearn: unknown estimator {estimator!r}",
            )
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"sklearn unavailable: {exc}")

    try:
        model.fit(X_tr, y_tr)
        preds = model.predict(X_te) if len(X_te) else np.array([])
        if estimator.endswith("regressor") or estimator == "linreg":
            score = float(model.score(X_te, y_te)) if len(X_te) else float("nan")
            metric_name = "r2"
        else:
            score = float(model.score(X_te, y_te)) if len(X_te) else float("nan")
            metric_name = "accuracy"
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"model.sklearn fit failed: {exc}")

    # Surface the predictions as the next executor's frame.
    out = df.copy()
    if len(preds):
        col = f"{target_col}_pred"
        all_preds = np.concatenate([np.full(split, np.nan), preds])
        out[col] = all_preds
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out),
            "estimator": estimator,
            "score": score,
        },
        metrics={"estimator": estimator, metric_name: score, "n_train": split, "n_test": n - split},
        log_label=f"sklearn:{estimator} {metric_name}={score:.3f}",
    )
