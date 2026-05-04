"""Experiment runners for quant-aware ML workflows."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import build_from_config, register
from aqp.ml.models._utils import prepare_panel, split_xy

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    run_name: str
    experiment_type: str
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    records: dict[str, Any] = field(default_factory=dict)
    prediction_sample: list[dict[str, Any]] = field(default_factory=list)
    mlflow_run_id: str | None = None
    run_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@register("Experiment")
class Experiment:
    """Build dataset/model configs, fit, predict, score, and log the run."""

    experiment_type = "generic"

    def __init__(
        self,
        dataset_cfg: dict[str, Any],
        model_cfg: dict[str, Any],
        run_name: str = "ml-experiment",
        records: list[dict[str, Any]] | None = None,
        segment: str = "test",
        lineage: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> None:
        self.dataset_cfg = dict(dataset_cfg or {})
        self.model_cfg = dict(model_cfg or {})
        self.run_name = str(run_name)
        self.records = list(records or [])
        self.segment = str(segment)
        self.lineage = dict(lineage or {})
        self.persist = bool(persist)
        self.dataset: Any | None = None
        self.model: Any | None = None

    def run(self, task_id: str | None = None) -> ExperimentResult:
        run_id = self._persist_start(task_id=task_id)
        try:
            self.dataset = build_from_config(self.dataset_cfg)
            self.model = build_from_config(self.model_cfg)
            if self.dataset is None or self.model is None:
                raise ValueError("dataset_cfg and model_cfg must resolve to objects")
            self.model.fit(self.dataset)
            pred = self.model.predict(self.dataset, segment=self.segment)
            if not isinstance(pred, pd.Series):
                pred = pd.Series(pred, name="score")
            metrics = self._metrics(pred)
            records = self._records(pred)
            sample_df = _prediction_sample(pred, self.dataset, self.segment)
            feature_importance = _feature_importance(self.model)
            from aqp.mlops.mlflow_client import log_ml_experiment_run

            mlflow_run_id = log_ml_experiment_run(
                run_name=self.run_name,
                experiment_type=self.experiment_type,
                params={
                    "dataset": self.dataset_cfg,
                    "model": self.model_cfg,
                    "lineage": self.lineage,
                },
                metrics=metrics,
                tags={
                    "task_id": task_id,
                    "model_class": self.model_cfg.get("class"),
                    "dataset_class": self.dataset_cfg.get("class"),
                    **self.lineage,
                },
                prediction_sample=sample_df,
                feature_importance=feature_importance,
                artifacts={"records": records},
            )
            result = ExperimentResult(
                run_name=self.run_name,
                experiment_type=self.experiment_type,
                status="completed",
                metrics=metrics,
                records=records,
                prediction_sample=sample_df.head(50).to_dict(orient="records"),
                mlflow_run_id=mlflow_run_id,
                run_id=run_id,
            )
            self._persist_done(run_id, result)
            return result
        except Exception as exc:
            logger.exception("ML experiment failed")
            result = ExperimentResult(
                run_name=self.run_name,
                experiment_type=self.experiment_type,
                status="failed",
                run_id=run_id,
                error=str(exc),
            )
            self._persist_done(run_id, result)
            raise

    def _metrics(self, pred: pd.Series) -> dict[str, Any]:
        metrics: dict[str, Any] = {"n_predictions": int(len(pred))}
        try:
            label = _label_for(self.dataset, self.segment)
            joined = pd.concat([pred.rename("pred"), label.rename("label")], axis=1).dropna()
            if not joined.empty:
                err = joined["pred"].astype(float) - joined["label"].astype(float)
                metrics.update(
                    {
                        "rmse": float(np.sqrt(np.mean(np.square(err)))),
                        "mae": float(np.mean(np.abs(err))),
                        "ic": float(joined["pred"].corr(joined["label"], method="spearman")),
                        "directional_accuracy": float(
                            (np.sign(joined["pred"]) == np.sign(joined["label"])).mean()
                        ),
                        "n_labels": int(len(joined)),
                    }
                )
        except Exception:
            logger.debug("basic metric calculation skipped", exc_info=True)
        return metrics

    def _records(self, pred: pd.Series) -> dict[str, Any]:
        del pred
        return {}

    def _persist_start(self, task_id: str | None) -> str | None:
        if not self.persist:
            return None
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import MLExperimentRun

            with get_session() as session:
                row = MLExperimentRun(
                    task_id=task_id,
                    run_name=self.run_name,
                    experiment_type=self.experiment_type,
                    status="running",
                    framework=_framework_from_model_cfg(self.model_cfg),
                    model_class=str(self.model_cfg.get("class") or ""),
                    experiment_plan_id=self.lineage.get("experiment_plan_id"),
                    dataset_version_id=self.lineage.get("dataset_version_id"),
                    split_plan_id=self.lineage.get("split_plan_id"),
                    pipeline_recipe_id=self.lineage.get("pipeline_recipe_id"),
                    dataset_hash=self.lineage.get("dataset_hash"),
                    params={"dataset": self.dataset_cfg, "model": self.model_cfg, "lineage": self.lineage},
                    started_at=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception:
            logger.debug("MLExperimentRun start persistence skipped", exc_info=True)
            return None

    def _persist_done(self, run_id: str | None, result: ExperimentResult) -> None:
        if not self.persist or not run_id:
            return
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import MLExperimentRun

            with get_session() as session:
                row = session.get(MLExperimentRun, run_id)
                if row is None:
                    return
                row.status = result.status
                row.metrics = result.metrics
                row.artifacts = result.records
                row.prediction_sample = result.prediction_sample
                row.mlflow_run_id = result.mlflow_run_id
                row.error = result.error
                row.completed_at = datetime.utcnow()
                session.add(row)
        except Exception:
            logger.debug("MLExperimentRun completion persistence skipped", exc_info=True)


@register("AlphaExperiment")
class AlphaExperiment(Experiment):
    """Experiment runner that evaluates model predictions as tradable alphas."""

    experiment_type = "alpha"

    def _records(self, pred: pd.Series) -> dict[str, Any]:
        del pred
        if self.model is None or self.dataset is None:
            return {}
        out: dict[str, Any] = {}
        try:
            from aqp.core.registry import build_from_config
            from aqp.ml.recorder import PortAnaRecord, SigAnaRecord, SignalRecord

            sig = SignalRecord(model=self.model, dataset=self.dataset)
            out["SignalRecord"] = sig.generate(segment=self.segment)
            if not self.records:
                self.records = [
                    {"class": "SigAnaRecord", "module_path": "aqp.ml.recorder", "kwargs": {}},
                    {"class": "PortAnaRecord", "module_path": "aqp.ml.recorder", "kwargs": {}},
                ]
            for rec_cfg in self.records:
                kwargs = {**(rec_cfg.get("kwargs") or {}), "signal_record": sig}
                rec = build_from_config({**rec_cfg, "kwargs": kwargs})
                if rec is not None:
                    out[str(rec_cfg.get("class"))] = rec.generate()
        except Exception:
            logger.debug("alpha record generation skipped", exc_info=True)
        return out


@register("ForecastExperiment")
class ForecastExperiment(Experiment):
    experiment_type = "forecast"


@register("ClassificationExperiment")
class ClassificationExperiment(Experiment):
    experiment_type = "classification"

    def _metrics(self, pred: pd.Series) -> dict[str, Any]:
        metrics = super()._metrics(pred)
        try:
            label = (_label_for(self.dataset, self.segment) > 0).astype(int)
            joined = pd.concat([pred.rename("score"), label.rename("label")], axis=1).dropna()
            if not joined.empty:
                cls = (joined["score"] >= 0.5).astype(int)
                metrics["accuracy"] = float((cls == joined["label"]).mean())
                tp = int(((cls == 1) & (joined["label"] == 1)).sum())
                fp = int(((cls == 1) & (joined["label"] == 0)).sum())
                fn = int(((cls == 0) & (joined["label"] == 1)).sum())
                metrics["precision"] = float(tp / max(1, tp + fp))
                metrics["recall"] = float(tp / max(1, tp + fn))
        except Exception:
            logger.debug("classification metrics skipped", exc_info=True)
        return metrics


@register("AnomalyExperiment")
class AnomalyExperiment(Experiment):
    experiment_type = "anomaly"

    def _metrics(self, pred: pd.Series) -> dict[str, Any]:
        values = pred.astype(float)
        return {
            "n_predictions": int(len(values)),
            "score_mean": float(values.mean()) if len(values) else 0.0,
            "score_std": float(values.std()) if len(values) else 0.0,
            "score_p95": float(values.quantile(0.95)) if len(values) else 0.0,
        }


def _label_for(dataset: Any, segment: str) -> pd.Series:
    raw = dataset.prepare(segment, col_set="label")
    if isinstance(raw, pd.Series):
        return raw.astype(float)
    if isinstance(raw, pd.DataFrame):
        if isinstance(raw.columns, pd.MultiIndex) and "label" in raw.columns.get_level_values(0):
            raw = raw["label"]
        return raw.iloc[:, 0].astype(float)
    raise TypeError("dataset label segment did not resolve to a Series/DataFrame")


def _prediction_sample(pred: pd.Series, dataset: Any, segment: str) -> pd.DataFrame:
    frame = pred.rename("score").reset_index()
    with pd.option_context("mode.use_inf_as_na", True):
        try:
            label = _label_for(dataset, segment)
            label_frame = label.rename("label").reset_index()
            frame = frame.merge(label_frame, how="left")
        except Exception:
            pass
    for col in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[col]):
            frame[col] = frame[col].astype(str)
    return frame.head(500)


def _feature_importance(model: Any) -> dict[str, float]:
    if hasattr(model, "feature_importance"):
        try:
            return dict(model.feature_importance())
        except Exception:
            return {}
    return {}


def _framework_from_model_cfg(model_cfg: dict[str, Any]) -> str | None:
    module = str(model_cfg.get("module_path") or "")
    if ".sklearn" in module:
        return "scikit-learn"
    if ".forecasting" in module:
        return "forecasting"
    if ".anomaly" in module:
        return "pyod"
    if ".keras" in module:
        return "keras"
    if ".huggingface" in module:
        return "transformers"
    if ".torch" in module:
        return "pytorch"
    if ".tree" in module:
        return "gbdt"
    return None


__all__ = [
    "AlphaExperiment",
    "AnomalyExperiment",
    "ClassificationExperiment",
    "Experiment",
    "ExperimentResult",
    "ForecastExperiment",
]
