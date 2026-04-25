"""ML-prediction-as-indicator adapter.

Bridges the :class:`aqp.persistence.models.ModelDeployment` registry into
the :class:`aqp.data.indicators_zoo.IndicatorZoo` feature surface so any
strategy / feature engineer can mix deployed-model predictions with
classical TA indicators in a single tidy frame.

Two consumption surfaces:

- ``"ModelPred:deployment_id=<uuid>,horizon=5"`` — referenced from a
  spec list, evaluated by :func:`apply_model_predictions` as a vectorised
  post-step inside :meth:`IndicatorZoo.transform`.
- ``ModelPredictionIndicator`` — direct callable for tests and notebooks
  that don't need a full deployment row (pass a pre-loaded model + an
  optional dataset config).

The vectorised path mirrors :class:`aqp.strategies.ml_alphas.DeployedModelAlpha`'s
dataset-driven inference path so the same predictions feed alpha
generation and feature engineering without drift.
"""
from __future__ import annotations

import logging
import pickle
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ModelPredictionSpec:
    """Parsed form of a ``ModelPred:...`` indicator spec."""

    deployment_id: str | None = None
    model_path: str | None = None
    segment: str = "infer"
    horizon: int | None = None
    column_name: str | None = None
    feature_specs: list[str] | None = None

    @classmethod
    def from_kwargs(cls, kwargs: dict[str, Any]) -> ModelPredictionSpec:
        feature_specs = kwargs.get("feature_specs") or kwargs.get("features")
        if isinstance(feature_specs, str):
            feature_specs = [s.strip() for s in feature_specs.split("|") if s.strip()]
        horizon = kwargs.get("horizon")
        if horizon is not None:
            try:
                horizon = int(horizon)
            except (TypeError, ValueError):
                horizon = None
        return cls(
            deployment_id=kwargs.get("deployment_id"),
            model_path=kwargs.get("model_path"),
            segment=str(kwargs.get("segment", "infer") or "infer"),
            horizon=horizon,
            column_name=kwargs.get("column_name") or kwargs.get("name"),
            feature_specs=list(feature_specs) if feature_specs else None,
        )


def is_model_pred_spec(name: str) -> bool:
    """Return ``True`` for any indicator alias that resolves to a model prediction."""
    if not name:
        return False
    return name.lower() in {"modelpred", "model_pred", "modelprediction"}


# ---------------------------------------------------------------------------
# Vectorised application path
# ---------------------------------------------------------------------------


def _column_for(spec: ModelPredictionSpec) -> str:
    if spec.column_name:
        return spec.column_name
    if spec.deployment_id:
        return f"model_pred_{spec.deployment_id[:8]}"
    if spec.model_path:
        return f"model_pred_{Path(spec.model_path).stem[:16]}"
    return "model_pred"


def _resolve_deployment_artifacts(spec: ModelPredictionSpec) -> tuple[Any, dict | None]:
    """Load ``(model, dataset_cfg)`` pair for a deployment-id spec.

    Falls back to ``(None, None)`` on any error so callers can degrade
    gracefully (the caller is expected to skip the indicator when the
    model isn't available rather than abort the whole transform).
    """
    if spec.deployment_id is None and spec.model_path is None:
        return None, None
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models import (
            ExperimentPlan,
            ModelDeployment,
            ModelVersion,
        )
        from aqp.mlops.model_registry import load_alpha_path
    except Exception:
        logger.exception("ModelPrediction: cannot import deployment registry")
        return None, None

    dataset_cfg: dict | None = None
    model_path: str | None = spec.model_path

    if spec.deployment_id is not None:
        try:
            with get_session() as session:
                deployment = session.get(ModelDeployment, spec.deployment_id)
                if deployment is None:
                    logger.warning(
                        "ModelPrediction: deployment %s not found", spec.deployment_id
                    )
                    return None, None
                model_row = session.get(ModelVersion, deployment.model_version_id)
                if model_row is None:
                    logger.warning(
                        "ModelPrediction: model version for %s not found",
                        spec.deployment_id,
                    )
                    return None, None
                if deployment.experiment_plan_id:
                    plan = session.get(ExperimentPlan, deployment.experiment_plan_id)
                    if plan and isinstance(plan.dataset_cfg, dict):
                        dataset_cfg = deepcopy(plan.dataset_cfg)
                cfg = deployment.deployment_config
                if isinstance(cfg, dict):
                    if isinstance(cfg.get("dataset_cfg"), dict):
                        dataset_cfg = deepcopy(cfg["dataset_cfg"])
                    if cfg.get("model_path") and not model_path:
                        model_path = str(cfg["model_path"])
                if not model_path:
                    raw = (
                        load_alpha_path(model_row.registry_name, stage="Production")
                        or load_alpha_path(model_row.registry_name, stage="Staging")
                    )
                    if raw:
                        candidate = str(raw)
                        if candidate.startswith("file://"):
                            candidate = candidate.replace("file://", "", 1)
                        path = Path(candidate)
                        if path.is_dir():
                            for f in path.glob("*.pkl"):
                                model_path = str(f)
                                break
                        elif path.is_file():
                            model_path = str(path)
        except Exception:
            logger.exception("ModelPrediction: deployment lookup failed")
            return None, None

    if not model_path:
        logger.warning("ModelPrediction: could not resolve model path for %s", spec.deployment_id)
        return None, dataset_cfg

    try:
        from aqp.ml.base import Serializable

        try:
            model = Serializable.from_pickle(model_path)
        except Exception:
            with open(model_path, "rb") as fh:
                model = pickle.load(fh)
    except Exception:
        logger.exception("ModelPrediction: model load failed")
        return None, dataset_cfg

    return model, dataset_cfg


def _predict_with_dataset(
    model: Any,
    dataset_cfg: dict,
    bars: pd.DataFrame,
    universe: list[str],
    segment: str,
) -> pd.Series | None:
    """Run dataset-driven inference and return a vt_symbol-indexed Series."""
    try:
        from aqp.core.registry import build_from_config
    except Exception:
        return None
    cfg = deepcopy(dataset_cfg)
    kwargs = cfg.setdefault("kwargs", {})
    handler = kwargs.get("handler")
    if isinstance(handler, dict):
        handler_kwargs = handler.setdefault("kwargs", {})
        handler_kwargs["instruments"] = universe
        if not bars.empty:
            ts = pd.to_datetime(bars["timestamp"])
            handler_kwargs["start_time"] = str(ts.min())
            handler_kwargs["end_time"] = str(ts.max())
            handler_kwargs.setdefault("fit_start_time", handler_kwargs["start_time"])
            handler_kwargs.setdefault("fit_end_time", handler_kwargs["end_time"])
    if "segments" not in kwargs and not bars.empty:
        ts = pd.to_datetime(bars["timestamp"])
        kwargs["segments"] = {segment: [str(ts.min()), str(ts.max())]}
    elif segment not in kwargs.get("segments", {}) and "test" in kwargs.get("segments", {}):
        kwargs["segments"][segment] = list(kwargs["segments"]["test"])

    try:
        dataset = build_from_config(cfg)
        pred = model.predict(dataset, segment=segment)
    except Exception:
        logger.exception("ModelPrediction: dataset predict failed")
        return None
    if not isinstance(pred, pd.Series):
        try:
            pred = pd.Series(pred)
        except Exception:
            return None
    return pred


def _predict_with_indicator_features(
    model: Any,
    bars: pd.DataFrame,
    feature_specs: list[str] | None,
) -> pd.DataFrame | None:
    """Fallback path — compute features via :class:`IndicatorZoo` and call ``model.predict``.

    Returns a frame with ``timestamp`` / ``vt_symbol`` / ``score`` so the
    caller can join it back to ``bars``.
    """
    if model is None or bars.empty:
        return None
    try:
        from aqp.data.indicators_zoo import IndicatorZoo

        zoo = IndicatorZoo()
        feats = zoo.transform(bars, indicators=feature_specs or None)
    except Exception:
        logger.exception("ModelPrediction: indicator-zoo features failed")
        return None
    drop_cols = {
        "timestamp",
        "vt_symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "target",
        "label",
    }
    feature_cols = [c for c in feats.columns if c.lower() not in drop_cols]
    if not feature_cols:
        return None
    X = feats[feature_cols].fillna(0).values
    try:
        if hasattr(model, "predict") and not hasattr(model, "fit"):
            module = getattr(model, "module", None)
            if module is None:
                return None
            import torch

            module.eval()
            with torch.no_grad():
                out = module(torch.tensor(X, dtype=torch.float32))
                if out.ndim > 1:
                    out = out.squeeze(-1)
                preds = out.cpu().numpy()
        else:
            preds = model.predict(X)
    except Exception:
        logger.exception("ModelPrediction: numeric predict failed")
        return None
    out = feats[["timestamp", "vt_symbol"]].copy()
    out["score"] = pd.to_numeric(preds, errors="coerce").fillna(0.0)
    return out


def apply_model_predictions(
    bars: pd.DataFrame,
    specs: list[tuple[str, dict[str, Any]]],
) -> pd.DataFrame:
    """Append one column per ``ModelPred:...`` spec to ``bars``.

    Parameters
    ----------
    bars
        Tidy long-format frame with ``timestamp`` and ``vt_symbol``.
    specs
        List of ``(alias, kwargs)`` pairs already filtered to model-pred
        aliases by :func:`is_model_pred_spec`.

    Returns
    -------
    pd.DataFrame
        ``bars`` plus one new column per spec; rows without a prediction
        are filled with ``NaN``.
    """
    if bars.empty or not specs:
        return bars
    out = bars
    for _alias, kwargs in specs:
        spec = ModelPredictionSpec.from_kwargs(kwargs)
        col = _column_for(spec)
        if col in out.columns:
            continue
        model, dataset_cfg = _resolve_deployment_artifacts(spec)
        if model is None:
            logger.info("ModelPrediction: skipping %s (no model available)", col)
            out[col] = float("nan")
            continue
        universe = sorted(out["vt_symbol"].astype(str).unique().tolist())
        pred_frame: pd.DataFrame | None = None
        if dataset_cfg:
            series = _predict_with_dataset(
                model, dataset_cfg, out, universe, spec.segment
            )
            if series is not None and not series.empty:
                pred_frame = series.reset_index(name="score")
                if "vt_symbol" not in pred_frame.columns:
                    cols = [c for c in pred_frame.columns if c != "score"]
                    if cols:
                        pred_frame = pred_frame.rename(columns={cols[-1]: "vt_symbol"})
                if "timestamp" not in pred_frame.columns and "datetime" in pred_frame.columns:
                    pred_frame = pred_frame.rename(columns={"datetime": "timestamp"})
        if pred_frame is None:
            pred_frame = _predict_with_indicator_features(
                model, out, spec.feature_specs
            )
        if pred_frame is None or pred_frame.empty:
            out[col] = float("nan")
            continue
        pred_frame = pred_frame.copy()
        if "timestamp" in pred_frame.columns:
            pred_frame["timestamp"] = pd.to_datetime(pred_frame["timestamp"])
            join_cols = ["timestamp", "vt_symbol"]
        else:
            # Fall back to a per-symbol latest-prediction broadcast.
            latest = pred_frame.groupby("vt_symbol", as_index=False)["score"].last()
            out = out.merge(
                latest.rename(columns={"score": col}),
                how="left",
                on="vt_symbol",
            )
            continue
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        out = out.merge(
            pred_frame[[*join_cols, "score"]].rename(columns={"score": col}),
            how="left",
            on=join_cols,
        )
    return out


# ---------------------------------------------------------------------------
# Direct indicator class — useful for tests + ad-hoc callers.
# ---------------------------------------------------------------------------


class ModelPredictionIndicator:
    """Minimal callable that mirrors :func:`apply_model_predictions` for one spec.

    Not a true online :class:`IndicatorBase` (predictions need a frame
    context, not a single-bar update). Provides ``transform`` so it can
    be substituted into pipelines that already accept that protocol.
    """

    def __init__(
        self,
        deployment_id: str | None = None,
        model_path: str | None = None,
        segment: str = "infer",
        horizon: int | None = None,
        column_name: str | None = None,
        feature_specs: list[str] | None = None,
    ) -> None:
        self.spec = ModelPredictionSpec(
            deployment_id=deployment_id,
            model_path=model_path,
            segment=segment,
            horizon=horizon,
            column_name=column_name,
            feature_specs=feature_specs,
        )

    def transform(self, bars: pd.DataFrame) -> pd.DataFrame:
        return apply_model_predictions(
            bars,
            specs=[("ModelPred", self.spec.__dict__)],
        )

    @property
    def column_name(self) -> str:
        return _column_for(self.spec)


__all__ = [
    "ModelPredictionIndicator",
    "ModelPredictionSpec",
    "apply_model_predictions",
    "is_model_pred_spec",
]
