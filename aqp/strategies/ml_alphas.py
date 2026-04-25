"""ML alpha models — thin :class:`IAlphaModel` wrappers over :mod:`aqp.ml.models`.

Each class takes a trained :class:`aqp.ml.base.Model` (or a path to a pickle
thereof) and produces :class:`aqp.core.types.Signal` objects from its
predictions at each bar.

The original public surface — ``XGBoostAlpha``, ``LightGBMAlpha`` — is
preserved for backwards compatibility. New wrappers provide the same
ergonomics for the deep-learning zoo (LSTM / GRU / ALSTM / Transformer /
TCN) so YAMLs don't need to know whether the backing model is a tree or
a neural net.
"""
from __future__ import annotations

import logging
import pickle
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


# Columns that are never treated as features when falling back to the
# legacy "one-shot prediction" path (i.e. no DatasetH wiring).
_NON_FEATURE_COLS = {
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


# ---------------------------------------------------------------------------
# Shared base.
# ---------------------------------------------------------------------------


class _MLBaseAlpha(IAlphaModel):
    """Shared alpha wrapper.

    Modes:

    - **Legacy path** — ``model_path`` points at a pickle of a scikit-learn
      style estimator with ``predict(X)``. Features are computed on the
      fly via :class:`aqp.data.indicators_zoo.IndicatorZoo`.
    - **New path** — ``model`` is a native :class:`aqp.ml.base.Model`.
      Features come from a :class:`aqp.ml.dataset.DatasetH` bound to the
      wrapper; we call ``model.predict(dataset, segment='infer')`` for the
      latest timestamp and translate the result into ``Signal`` rows.
    """

    def __init__(
        self,
        feature_specs: list[str] | None = None,
        model_path: str | Path | None = None,
        model: Any | None = None,
        long_threshold: float = 0.001,
        short_threshold: float = -0.001,
        allow_short: bool = True,
        top_k: int | None = None,
        feature_set_name: str | None = None,
    ) -> None:
        self.feature_specs = list(feature_specs or [])
        self.feature_set_name = feature_set_name
        self.model_path = Path(model_path) if model_path else None
        self.long_threshold = float(long_threshold)
        self.short_threshold = float(short_threshold)
        self.allow_short = bool(allow_short)
        self.top_k = int(top_k) if top_k else None
        self._model: Any | None = model
        if model is None and self.model_path and self.model_path.exists():
            self._load()

    # ------------------------------------------------------------------ io --

    def _load(self) -> None:
        try:
            with self.model_path.open("rb") as fh:  # type: ignore[union-attr]
                self._model = pickle.load(fh)
        except Exception:
            logger.exception("could not load ML alpha model at %s", self.model_path)
            self._model = None

    # ----------------------------------------------------------- features --

    def _features_for(self, bars: pd.DataFrame) -> pd.DataFrame:
        if self.feature_set_name:
            try:
                from aqp.data.feature_sets import FeatureSetService

                service = FeatureSetService()
                summary = service.get_by_name(self.feature_set_name)
                if summary is not None:
                    return service.materialize(summary.id, bars)
                logger.warning(
                    "feature_set_name=%s not found; falling back to feature_specs",
                    self.feature_set_name,
                )
            except Exception:
                logger.exception("FeatureSetService materialize failed; using IndicatorZoo")
        from aqp.data.indicators_zoo import IndicatorZoo

        zoo = IndicatorZoo()
        specs = self.feature_specs if self.feature_specs else None
        return zoo.transform(bars, indicators=specs)

    # ------------------------------------------------------------ signals --

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if self._model is None or bars.empty:
            return []
        feats = self._features_for(bars)
        universe_set = {s.vt_symbol for s in universe}
        now = context.get("current_time")
        latest = feats.sort_values("timestamp").groupby("vt_symbol").tail(1)
        if latest.empty:
            return []
        feature_cols = [c for c in latest.columns if c.lower() not in _NON_FEATURE_COLS]
        x = latest[feature_cols].fillna(0).values
        try:
            preds = self._predict(x)
        except Exception:
            logger.exception("%s inference failed", type(self).__name__)
            return []
        preds = np.asarray(preds, dtype=float).reshape(-1)

        # Map predictions back to symbols + pick top-K if configured.
        rows = list(latest.iterrows())
        if self.top_k:
            order = np.argsort(-preds)
            kept = set(order[: self.top_k])
            rows = [rows[i] for i in range(len(rows)) if i in kept]
            preds = np.asarray([preds[i] for i in range(len(preds)) if i in kept])

        signals: list[Signal] = []
        for (_, row), pred in zip(rows, preds, strict=False):
            vt = row["vt_symbol"]
            if vt not in universe_set:
                continue
            pred = float(pred)
            direction = None
            if pred >= self.long_threshold:
                direction = Direction.LONG
            elif pred <= self.short_threshold and self.allow_short:
                direction = Direction.SHORT
            if direction is None:
                continue
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt),
                    strength=float(min(1.0, abs(pred) * 10)),
                    direction=direction,
                    timestamp=now or row["timestamp"],
                    confidence=float(min(1.0, abs(pred) * 20)),
                    source=type(self).__name__,
                    rationale=f"pred={pred:.4f}",
                )
            )
        return signals

    # ----------------------------------------------------- estimator hook --

    def _predict(self, x: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("model is not loaded")
        if hasattr(self._model, "predict") and not hasattr(self._model, "fit"):
            # Native aqp.ml.base.Model — predict expects a Dataset not an
            # array; fall back to raw numpy via ``_model.module`` if we've
            # got a torch wrapper, else bail out.
            module = getattr(self._model, "module", None)
            if module is not None:
                import torch

                module.eval()
                with torch.no_grad():
                    out = module(torch.tensor(x, dtype=torch.float32))
                    if out.ndim > 1:
                        out = out.squeeze(-1)
                    return out.cpu().numpy()
            raise RuntimeError(
                f"{type(self).__name__}: cannot run inference on numpy features "
                "without a legacy sklearn-style booster. Train via aqp.ml.models "
                "and pass the trained instance via `model=...` plus a DatasetH."
            )
        return self._model.predict(x)


# ---------------------------------------------------------------------------
# Concrete wrappers.
# ---------------------------------------------------------------------------


@register("XGBoostAlpha")
class XGBoostAlpha(_MLBaseAlpha):
    """Gradient-boosted-trees alpha via ``xgboost``."""

    def train(
        self,
        bars: pd.DataFrame,
        forward_horizon_days: int = 5,
        **model_kwargs: Any,
    ) -> dict[str, Any]:
        import xgboost as xgb

        feats = self._features_for(bars)
        feats = feats.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)
        feats["target"] = (
            feats.groupby("vt_symbol")["close"].shift(-forward_horizon_days)
            / feats["close"]
            - 1
        )
        train = feats.dropna(subset=["target"]).copy()
        feature_cols = [c for c in train.columns if c.lower() not in _NON_FEATURE_COLS]
        X = train[feature_cols].fillna(0).values
        y = train["target"].fillna(0).values

        params = {
            "max_depth": 5,
            "learning_rate": 0.05,
            "n_estimators": 200,
            "objective": "reg:squarederror",
            "n_jobs": -1,
            **model_kwargs,
        }
        self._model = xgb.XGBRegressor(**params)
        self._model.fit(X, y)
        if self.model_path:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            with self.model_path.open("wb") as fh:
                pickle.dump(self._model, fh)

        preds = self._model.predict(X)
        metrics = {
            "rmse": float(np.sqrt(np.mean((preds - y) ** 2))),
            "ic": float(pd.Series(preds).corr(pd.Series(y), method="spearman")),
            "n_rows": int(len(train)),
            "n_features": int(len(feature_cols)),
        }
        self._mlflow_autolog(metrics, feature_cols)
        return metrics

    def _mlflow_autolog(self, metrics: dict[str, Any], features: list[str]) -> None:
        try:
            from aqp.mlops.model_registry import register_alpha

            if self.model_path:
                register_alpha(
                    name=type(self).__name__,
                    alpha_path=self.model_path,
                    metrics=metrics,
                    meta={"features": features, "feature_specs": self.feature_specs},
                )
        except Exception:
            logger.debug("MLflow registry skipped for %s", type(self).__name__, exc_info=True)


@register("LightGBMAlpha")
class LightGBMAlpha(XGBoostAlpha):
    """Gradient-boosted-trees alpha via ``lightgbm``. Reuses XGBoost's wrapper
    with a different ``train()`` routine."""

    def train(
        self,
        bars: pd.DataFrame,
        forward_horizon_days: int = 5,
        **model_kwargs: Any,
    ) -> dict[str, Any]:
        import lightgbm as lgb

        feats = self._features_for(bars)
        feats = feats.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)
        feats["target"] = (
            feats.groupby("vt_symbol")["close"].shift(-forward_horizon_days)
            / feats["close"]
            - 1
        )
        train = feats.dropna(subset=["target"]).copy()
        feature_cols = [c for c in train.columns if c.lower() not in _NON_FEATURE_COLS]
        X = train[feature_cols].fillna(0).values
        y = train["target"].fillna(0).values

        params = {
            "n_estimators": 200,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "objective": "regression",
            "n_jobs": -1,
            "verbose": -1,
            **model_kwargs,
        }
        self._model = lgb.LGBMRegressor(**params)
        self._model.fit(X, y)
        if self.model_path:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            with self.model_path.open("wb") as fh:
                pickle.dump(self._model, fh)

        preds = self._model.predict(X)
        metrics = {
            "rmse": float(np.sqrt(np.mean((preds - y) ** 2))),
            "ic": float(pd.Series(preds).corr(pd.Series(y), method="spearman")),
            "n_rows": int(len(train)),
            "n_features": int(len(feature_cols)),
        }
        self._mlflow_autolog(metrics, feature_cols)
        return metrics


@register("LSTMAlpha")
class LSTMAlpha(_MLBaseAlpha):
    """Alpha wrapper over a trained :class:`aqp.ml.models.torch.LSTMModel`."""

    def __init__(
        self,
        model: Any | None = None,
        model_path: str | Path | None = None,
        feature_specs: list[str] | None = None,
        long_threshold: float = 0.001,
        short_threshold: float = -0.001,
        allow_short: bool = True,
        top_k: int | None = None,
    ) -> None:
        super().__init__(
            feature_specs=feature_specs,
            model_path=model_path,
            model=model,
            long_threshold=long_threshold,
            short_threshold=short_threshold,
            allow_short=allow_short,
            top_k=top_k,
        )


@register("GRUAlpha")
class GRUAlpha(LSTMAlpha):
    """Alpha wrapper over a trained :class:`aqp.ml.models.torch.GRUModel`."""


@register("TransformerAlpha")
class TransformerAlpha(LSTMAlpha):
    """Alpha wrapper over a trained :class:`aqp.ml.models.torch.TransformerModel`."""


@register("TCNAlpha")
class TCNAlpha(LSTMAlpha):
    """Alpha wrapper over a trained :class:`aqp.ml.models.torch.TCNModel`."""


@register("DeployedModelAlpha")
class DeployedModelAlpha(_MLBaseAlpha):
    """Deployment-backed model alpha.

    Prefers dataset-driven inference (`model.predict(dataset, segment='infer')`)
    when a deployment carries an experiment dataset recipe. Falls back to the
    legacy indicator-zoo numpy path so existing strategy configs remain valid.
    """

    def __init__(
        self,
        deployment_id: str,
        infer_segment: str = "infer",
        model_path: str | Path | None = None,
        feature_specs: list[str] | None = None,
        long_threshold: float = 0.001,
        short_threshold: float = -0.001,
        allow_short: bool = True,
        top_k: int | None = None,
    ) -> None:
        super().__init__(
            feature_specs=feature_specs,
            model_path=model_path,
            model=None,
            long_threshold=long_threshold,
            short_threshold=short_threshold,
            allow_short=allow_short,
            top_k=top_k,
        )
        self.deployment_id = deployment_id
        self.infer_segment = infer_segment
        self._dataset_cfg: dict[str, Any] | None = None
        self._loaded = False

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        self._ensure_loaded()
        if self._model is None or bars.empty:
            return []
        if self._dataset_cfg:
            try:
                return self._generate_dataset_signals(bars, universe, context)
            except Exception:
                logger.exception(
                    "DeployedModelAlpha dataset-driven inference failed; using legacy fallback"
                )
        return super().generate_signals(bars=bars, universe=universe, context=context)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            from aqp.ml.base import Serializable
            from aqp.mlops.model_registry import load_alpha_path
            from aqp.persistence.db import get_session
            from aqp.persistence.models import ExperimentPlan, ModelDeployment, ModelVersion

            with get_session() as session:
                deployment = session.get(ModelDeployment, self.deployment_id)
                if deployment is None:
                    raise RuntimeError(f"deployment {self.deployment_id!r} not found")
                model_row = session.get(ModelVersion, deployment.model_version_id)
                if model_row is None:
                    raise RuntimeError(
                        f"model version {deployment.model_version_id!r} not found"
                    )
                plan = (
                    session.get(ExperimentPlan, deployment.experiment_plan_id)
                    if deployment.experiment_plan_id
                    else None
                )

                # Deployment defaults override class defaults.
                self.long_threshold = float(deployment.long_threshold)
                self.short_threshold = float(deployment.short_threshold)
                self.allow_short = bool(deployment.allow_short)
                if deployment.top_k:
                    self.top_k = int(deployment.top_k)
                self.infer_segment = deployment.infer_segment or self.infer_segment

                if plan and isinstance(plan.dataset_cfg, dict):
                    self._dataset_cfg = deepcopy(plan.dataset_cfg)
                if isinstance(deployment.deployment_config, dict):
                    cfg = deployment.deployment_config
                    if isinstance(cfg.get("dataset_cfg"), dict):
                        self._dataset_cfg = deepcopy(cfg["dataset_cfg"])
                    if cfg.get("feature_specs") and not self.feature_specs:
                        self.feature_specs = list(cfg.get("feature_specs") or [])
                    custom_model_path = cfg.get("model_path")
                    if custom_model_path:
                        self.model_path = Path(custom_model_path)

                path = self._resolve_model_path(model_row.registry_name, load_alpha_path)
                if path:
                    try:
                        self._model = Serializable.from_pickle(path)
                    except Exception:
                        with Path(path).open("rb") as fh:
                            self._model = pickle.load(fh)
        except Exception:
            logger.exception("DeployedModelAlpha bootstrap failed")
            self._model = self._model if self._model is not None else None

    def _resolve_model_path(self, registry_name: str, loader) -> str | None:
        if self.model_path and self.model_path.exists():
            return str(self.model_path)
        raw = loader(registry_name, stage="Production") or loader(registry_name, stage="Staging")
        if not raw:
            return None
        candidate = str(raw)
        if candidate.startswith("file://"):
            candidate = candidate.replace("file://", "", 1)
        path = Path(candidate)
        if path.is_file():
            return str(path)
        if path.is_dir():
            for file in path.glob("*.pkl"):
                return str(file)
        return None

    def _generate_dataset_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        from aqp.core.registry import build_from_config

        if self._dataset_cfg is None:
            return []
        dataset_cfg = deepcopy(self._dataset_cfg)
        kwargs = dataset_cfg.setdefault("kwargs", {})
        handler = kwargs.get("handler")
        if isinstance(handler, dict):
            handler_kwargs = handler.setdefault("kwargs", {})
            handler_kwargs["instruments"] = [s.vt_symbol for s in universe]
            if not bars.empty:
                handler_kwargs["start_time"] = str(pd.to_datetime(bars["timestamp"]).min())
                handler_kwargs["end_time"] = str(pd.to_datetime(bars["timestamp"]).max())
                handler_kwargs.setdefault("fit_start_time", handler_kwargs["start_time"])
                handler_kwargs.setdefault("fit_end_time", handler_kwargs["end_time"])

        if "segments" not in kwargs:
            now = pd.to_datetime(bars["timestamp"]).max()
            start = pd.to_datetime(bars["timestamp"]).min()
            kwargs["segments"] = {"infer": [str(start), str(now)]}
        elif "infer" not in kwargs["segments"] and "test" in kwargs["segments"]:
            kwargs["segments"]["infer"] = list(kwargs["segments"]["test"])

        dataset = build_from_config(dataset_cfg)
        segment = self.infer_segment
        try:
            pred = self._model.predict(dataset, segment=segment)
        except Exception:
            pred = self._model.predict(dataset, segment="test")
            segment = "test"
        if not isinstance(pred, pd.Series):
            pred = pd.Series(pred)

        pred_df = pred.reset_index(name="score")
        if pred_df.empty:
            return []
        if "vt_symbol" not in pred_df.columns:
            pred_df["vt_symbol"] = pred_df.iloc[:, 1] if pred_df.shape[1] > 1 else "UNKNOWN"
        pred_df["score"] = pd.to_numeric(pred_df["score"], errors="coerce").fillna(0.0)
        latest = pred_df.groupby("vt_symbol", as_index=False)["score"].last()
        latest = latest.sort_values("score", ascending=False)
        if self.top_k:
            latest = latest.head(int(self.top_k))

        now = context.get("current_time")
        if now is None and not bars.empty:
            now = pd.to_datetime(bars["timestamp"]).max()
        universe_set = {s.vt_symbol for s in universe}
        signals: list[Signal] = []
        for _, row in latest.iterrows():
            vt_symbol = str(row["vt_symbol"])
            if vt_symbol not in universe_set:
                continue
            pred_val = float(row["score"])
            direction = None
            if pred_val >= self.long_threshold:
                direction = Direction.LONG
            elif pred_val <= self.short_threshold and self.allow_short:
                direction = Direction.SHORT
            if direction is None:
                continue
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt_symbol),
                    strength=float(min(1.0, abs(pred_val) * 10)),
                    direction=direction,
                    timestamp=now,
                    confidence=float(min(1.0, abs(pred_val) * 20)),
                    source=type(self).__name__,
                    rationale=f"deployment={self.deployment_id} segment={segment} pred={pred_val:.4f}",
                )
            )
        return signals
