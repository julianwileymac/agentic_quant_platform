"""``alpha.ml`` — apply a registered MLflow model to a feature panel.

The user picks a model by ``models:/<name>/<stage>`` URI (e.g.
``models:/long_short_mom/Production``) or by ``model_uri`` /
``run_id`` + ``artifact_path``. The executor loads the model through
``mlflow.pyfunc.load_model``, applies it to the upstream PANEL frame,
and emits a SIGNAL frame the downstream ``strategy.vbt_portfolio``
node can consume.

Params:

- ``model_uri`` (str, required) — any MLflow URI accepted by
  ``mlflow.pyfunc.load_model``.
- ``feature_columns`` (list[str], optional) — defaults to all
  numeric columns in the upstream frame.
- ``signal_clip`` (float, optional) — clip predictions to
  ``[-clip, +clip]`` so a noisy regressor doesn't blow the
  downstream portfolio's risk budget.
- ``output_column`` (str, default ``"signal"``) — name of the
  predicted column on the emitted SIGNAL frame.

Honours rule 2 (no direct LLM calls) and rule 22 (no direct ORM
reads from agent bodies). MLflow itself is the model registry.
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
    model_uri = str(params.get("model_uri") or "").strip()
    if not model_uri:
        return NodeResult(
            status="error",
            error="alpha.ml requires params.model_uri (e.g. models:/long_short_mom/Production)",
            log_label="alpha.ml:missing_uri",
        )
    output_column = str(params.get("output_column") or "signal")
    requested_features = params.get("feature_columns")
    signal_clip = params.get("signal_clip")

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(
            status="error",
            error="alpha.ml requires an upstream PANEL frame",
            log_label="alpha.ml:no_upstream",
        )

    feature_cols = numeric_columns(df, requested_features if isinstance(requested_features, list) else None)
    if not feature_cols:
        return NodeResult(
            status="error",
            error="alpha.ml: no numeric feature columns on the upstream frame",
            log_label="alpha.ml:no_features",
        )

    try:
        import mlflow  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"mlflow not installed: {exc}",
            log_label="alpha.ml:no_mlflow",
        )

    try:
        # ``mlflow.pyfunc.load_model`` honours the tracking URI in
        # settings; the autolog hook already sets the URI from
        # ``settings.mlflow_tracking_uri``.
        model = mlflow.pyfunc.load_model(model_uri)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"mlflow load_model({model_uri!r}) failed: {exc}",
            log_label="alpha.ml:load_fail",
        )

    try:
        preds = model.predict(df[feature_cols])
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"alpha.ml: model.predict failed: {exc}",
            log_label="alpha.ml:predict_fail",
        )

    preds_arr = np.asarray(preds).ravel().astype(float)
    if preds_arr.shape[0] != len(df):
        return NodeResult(
            status="error",
            error=(
                f"alpha.ml: model returned {preds_arr.shape[0]} preds for {len(df)} rows"
            ),
            log_label="alpha.ml:shape_mismatch",
        )
    if signal_clip is not None:
        try:
            clip = float(signal_clip)
            preds_arr = np.clip(preds_arr, -clip, clip)
        except (TypeError, ValueError):
            pass

    out = pd.DataFrame({output_column: preds_arr})
    if "datetime" in df.columns:
        out.insert(0, "datetime", df["datetime"].values)
    elif "ts" in df.columns:
        out.insert(0, "ts", df["ts"].values)
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out, kind="signal"),
            "model_uri": model_uri,
            "n_features": len(feature_cols),
            "output_column": output_column,
        },
        metrics={
            "rows": int(len(out)),
            "n_features": int(len(feature_cols)),
            "signal_mean": float(np.nanmean(preds_arr)) if preds_arr.size else 0.0,
            "signal_std": float(np.nanstd(preds_arr, ddof=1)) if preds_arr.size > 1 else 0.0,
        },
        log_label=f"alpha.ml:{model_uri}",
    )


__all__ = ["execute"]
