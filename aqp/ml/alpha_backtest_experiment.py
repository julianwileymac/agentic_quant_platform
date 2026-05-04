"""``AlphaBacktestExperiment`` — combined ML + backtest experiment runner.

This is the keystone "model used as alpha" experiment unit. A single
``AlphaBacktestExperiment.run(...)`` call:

1. Trains a model under an MLflow parent run (child run ``ml_train``).
2. Registers a :class:`aqp.persistence.models.ModelVersion`.
3. Optionally provisions a :class:`aqp.persistence.models.ModelDeployment`
   so the strategy below can reference it through ``DeployedModelAlpha``.
4. Runs the configured backtest under the same MLflow parent run
   (child run ``backtest``).
5. Computes combined ML + trading metrics with
   :mod:`aqp.ml.alpha_metrics` and persists a
   :class:`aqp.persistence.models.MLAlphaBacktestRun` row that links
   the new ``ModelVersion``, the ``MLExperimentRun``, and the
   ``BacktestRun`` together.

All MLflow logging goes through :mod:`aqp.mlops.mlflow_client` helpers,
all progress through :mod:`aqp.tasks._progress`, and all model
registration through :func:`aqp.mlops.model_registry.register_alpha`
per the platform hard rules.
"""
from __future__ import annotations

import contextlib
import logging
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.config import settings
from aqp.core.registry import build_from_config, register
from aqp.ml.alpha_metrics import (
    combined_score,
    compute_alpha_metrics,
    compute_attribution,
    compute_trading_metrics,
)

logger = logging.getLogger(__name__)


@dataclass
class AlphaBacktestResult:
    """Structured outcome of an ``AlphaBacktestExperiment`` run."""

    run_name: str
    status: str
    ml_metrics: dict[str, Any] = field(default_factory=dict)
    trading_metrics: dict[str, Any] = field(default_factory=dict)
    combined_metrics: dict[str, Any] = field(default_factory=dict)
    attribution: dict[str, Any] = field(default_factory=dict)
    mlflow_run_id: str | None = None
    ml_experiment_run_id: str | None = None
    backtest_run_id: str | None = None
    model_version_id: str | None = None
    model_deployment_id: str | None = None
    run_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@register("AlphaBacktestExperiment")
class AlphaBacktestExperiment:
    """Combined ML training + backtest experiment.

    Workflow:

    1. ``train_first=True`` (default): train the model from
       ``dataset_cfg`` + ``model_cfg``, register a ``ModelVersion``,
       and optionally provision a ``ModelDeployment``.
    2. ``train_first=False``: skip training and use an existing
       ``deployment_id`` (the model was trained earlier).
    3. Either way, run the backtest defined by ``strategy_cfg`` +
       ``backtest_cfg``, with the strategy's ``alpha_model`` block
       updated to reference the deployment so
       :class:`aqp.strategies.ml_alphas.DeployedModelAlpha` picks it up.
    4. Compute combined ML + trading metrics and persist the result.
    """

    def __init__(
        self,
        *,
        dataset_cfg: dict[str, Any] | None = None,
        model_cfg: dict[str, Any] | None = None,
        strategy_cfg: dict[str, Any],
        backtest_cfg: dict[str, Any],
        run_name: str = "alpha-backtest",
        segment: str = "test",
        train_first: bool = True,
        deployment_id: str | None = None,
        deployment_overrides: dict[str, Any] | None = None,
        capture_predictions: bool = True,
        records: list[dict[str, Any]] | None = None,
        lineage: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> None:
        self.dataset_cfg = dict(dataset_cfg or {})
        self.model_cfg = dict(model_cfg or {})
        self.strategy_cfg = deepcopy(strategy_cfg or {})
        self.backtest_cfg = deepcopy(backtest_cfg or {})
        self.run_name = str(run_name)
        self.segment = str(segment)
        self.train_first = bool(train_first)
        self.deployment_id = deployment_id
        self.deployment_overrides = dict(deployment_overrides or {})
        self.capture_predictions = bool(capture_predictions)
        self.records = list(records or [])
        self.lineage = dict(lineage or {})
        self.persist = bool(persist)

        if not self.train_first and not self.deployment_id:
            raise ValueError(
                "AlphaBacktestExperiment requires either train_first=True "
                "or an existing deployment_id"
            )
        if self.train_first:
            if not self.dataset_cfg:
                raise ValueError("dataset_cfg is required when train_first=True")
            if not self.model_cfg:
                raise ValueError("model_cfg is required when train_first=True")

        self._dataset: Any | None = None
        self._model: Any | None = None
        self._predictions: pd.Series | None = None

    def run(self, task_id: str | None = None) -> AlphaBacktestResult:
        from aqp.mlops.mlflow_client import (
            ensure_experiment,
            experiment_name_for_strategy,
            log_alpha_backtest_parent,
        )

        run_id = self._persist_start(task_id=task_id)
        result = AlphaBacktestResult(
            run_name=self.run_name, status="running", run_id=run_id
        )
        try:
            ensure_experiment(experiment_name_for_strategy(self.lineage.get("strategy_id")))
            with log_alpha_backtest_parent(
                run_name=self.run_name, lineage=self.lineage, params=self._params_snapshot()
            ) as parent:
                result.mlflow_run_id = parent.run_id

                model_version_id = None
                ml_run_id = None
                if self.train_first:
                    train_out = self._train_and_register(
                        task_id=task_id, parent_run_id=parent.run_id
                    )
                    result.ml_metrics = train_out.get("metrics") or {}
                    model_version_id = train_out.get("model_version_id")
                    ml_run_id = train_out.get("ml_experiment_run_id")
                    result.model_version_id = model_version_id
                    result.ml_experiment_run_id = ml_run_id
                    deployment_id = self._ensure_deployment(model_version_id)
                else:
                    deployment_id = self.deployment_id
                    if deployment_id:
                        info = self._lookup_deployment_info(deployment_id)
                        result.model_version_id = info.get("model_version_id")
                        model_version_id = info.get("model_version_id")
                result.model_deployment_id = deployment_id

                bt_out = self._run_backtest(
                    deployment_id=deployment_id,
                    parent_run_id=parent.run_id,
                    model_version_id=model_version_id,
                    ml_experiment_run_id=ml_run_id,
                )
                result.backtest_run_id = bt_out.get("backtest_run_id")
                result.trading_metrics = bt_out.get("metrics") or {}

                # Top-up ML metrics from cached predictions if we trained.
                if self._predictions is not None and not result.ml_metrics:
                    try:
                        labels = _label_for(self._dataset, self.segment)
                        result.ml_metrics = compute_alpha_metrics(
                            self._predictions, labels
                        )
                    except Exception:
                        logger.debug("Late ML metric computation skipped", exc_info=True)

                result.attribution = compute_attribution(
                    self._predictions, bt_out.get("timeline")
                )
                result.combined_metrics = self._build_combined_metrics(
                    result.ml_metrics, result.trading_metrics
                )

                # Log the rolled-up metrics on the parent run.
                with contextlib.suppress(Exception):
                    parent.log_metrics(result.combined_metrics)

                if self.capture_predictions and result.run_id:
                    self._persist_predictions(result.run_id, bt_out.get("timeline"))

                result.status = "completed"
            self._persist_done(result)
            return result
        except Exception as exc:
            logger.exception("AlphaBacktestExperiment failed")
            result.status = "failed"
            result.error = str(exc)
            self._persist_done(result)
            raise

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _train_and_register(
        self, task_id: str | None, parent_run_id: str | None
    ) -> dict[str, Any]:
        from aqp.mlops.mlflow_client import log_ml_experiment_run
        from aqp.mlops.model_registry import register_alpha as _register_alpha
        from aqp.persistence.db import get_session
        from aqp.persistence.models import MLExperimentRun, ModelVersion

        self._dataset = build_from_config(self.dataset_cfg)
        self._model = build_from_config(self.model_cfg)
        if self._dataset is None or self._model is None:
            raise ValueError("dataset_cfg and model_cfg must resolve to objects")

        self._model.fit(self._dataset)
        try:
            preds = self._model.predict(self._dataset, segment=self.segment)
        except Exception:
            preds = None
        if preds is not None and not isinstance(preds, pd.Series):
            preds = pd.Series(preds, name="score")
        self._predictions = preds

        ml_metrics: dict[str, Any] = {}
        sample_df = pd.DataFrame()
        if preds is not None:
            try:
                labels = _label_for(self._dataset, self.segment)
                ml_metrics = compute_alpha_metrics(preds, labels)
                sample_df = _prediction_sample(preds, labels)
            except Exception:
                logger.debug("training-time ML metrics skipped", exc_info=True)

        ml_run_id = log_ml_experiment_run(
            run_name=f"{self.run_name}/ml_train",
            experiment_type="alpha_backtest_train",
            params={"dataset": self.dataset_cfg, "model": self.model_cfg},
            metrics=ml_metrics,
            tags={
                "task_id": task_id,
                "parent_run_id": parent_run_id,
                "model_class": self.model_cfg.get("class"),
            },
            prediction_sample=sample_df if not sample_df.empty else None,
        )

        registry_name = f"{self.model_cfg.get('class', 'Model')}-{self.run_name}"
        with tempfile.TemporaryDirectory() as tmp:
            pkl = Path(tmp) / f"{registry_name}.pkl"
            with contextlib.suppress(Exception):
                self._model.to_pickle(pkl)
                _register_alpha(
                    name=registry_name,
                    alpha_path=pkl,
                    metrics={k: v for k, v in ml_metrics.items() if isinstance(v, (int, float))},
                    meta={
                        "run_name": self.run_name,
                        "model_class": self.model_cfg.get("class"),
                        **self.lineage,
                    },
                )

        model_version_id: str | None = None
        ml_experiment_run_id: str | None = None
        try:
            with get_session() as session:
                model_row = ModelVersion(
                    registry_name=registry_name,
                    mlflow_version=ml_run_id or "local",
                    stage="None",
                    algo=str(self.model_cfg.get("class")),
                    dataset_version_id=self.lineage.get("dataset_version_id"),
                    split_plan_id=self.lineage.get("split_plan_id"),
                    pipeline_recipe_id=self.lineage.get("pipeline_recipe_id"),
                    experiment_plan_id=self.lineage.get("experiment_plan_id"),
                    metrics=ml_metrics,
                    created_at=datetime.utcnow(),
                )
                session.add(model_row)
                session.flush()
                model_version_id = model_row.id

                ml_row = MLExperimentRun(
                    task_id=task_id,
                    run_name=f"{self.run_name}/ml_train",
                    experiment_type="alpha_backtest_train",
                    status="completed",
                    framework=_framework_from_model_cfg(self.model_cfg),
                    model_class=str(self.model_cfg.get("class") or ""),
                    model_version_id=model_version_id,
                    experiment_plan_id=self.lineage.get("experiment_plan_id"),
                    dataset_version_id=self.lineage.get("dataset_version_id"),
                    split_plan_id=self.lineage.get("split_plan_id"),
                    pipeline_recipe_id=self.lineage.get("pipeline_recipe_id"),
                    dataset_hash=self.lineage.get("dataset_hash"),
                    mlflow_run_id=ml_run_id,
                    params={"dataset": self.dataset_cfg, "model": self.model_cfg},
                    metrics=ml_metrics,
                    artifacts={"records": self.records},
                    prediction_sample=sample_df.head(50).to_dict(orient="records") if not sample_df.empty else [],
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                )
                session.add(ml_row)
                session.flush()
                ml_experiment_run_id = ml_row.id
        except Exception:
            logger.warning("ModelVersion / MLExperimentRun persistence skipped", exc_info=True)

        return {
            "metrics": ml_metrics,
            "model_version_id": model_version_id,
            "ml_experiment_run_id": ml_experiment_run_id,
        }

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    def _ensure_deployment(self, model_version_id: str | None) -> str | None:
        if self.deployment_id:
            return self.deployment_id
        if not model_version_id:
            return None
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import ModelDeployment

            overrides = self.deployment_overrides or {}
            deployment_cfg = dict(overrides.get("deployment_config") or {})
            if self.dataset_cfg and "dataset_cfg" not in deployment_cfg:
                deployment_cfg["dataset_cfg"] = self.dataset_cfg
            with get_session() as session:
                row = ModelDeployment(
                    name=str(overrides.get("name") or f"alpha-bt-{self.run_name}"),
                    status=str(overrides.get("status") or "staging"),
                    model_version_id=model_version_id,
                    experiment_plan_id=self.lineage.get("experiment_plan_id"),
                    dataset_version_id=self.lineage.get("dataset_version_id"),
                    split_plan_id=self.lineage.get("split_plan_id"),
                    pipeline_recipe_id=self.lineage.get("pipeline_recipe_id"),
                    alpha_class=str(overrides.get("alpha_class") or "DeployedModelAlpha"),
                    infer_segment=str(overrides.get("infer_segment") or self.segment),
                    long_threshold=float(overrides.get("long_threshold", 0.001)),
                    short_threshold=float(overrides.get("short_threshold", -0.001)),
                    allow_short=bool(overrides.get("allow_short", True)),
                    top_k=overrides.get("top_k"),
                    deployment_config=deployment_cfg,
                    meta={"run_name": self.run_name, **self.lineage},
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception:
            logger.warning("ModelDeployment provisioning skipped", exc_info=True)
            return None

    def _lookup_deployment_info(self, deployment_id: str) -> dict[str, Any]:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import ModelDeployment

            with get_session() as session:
                row = session.get(ModelDeployment, deployment_id)
                if row is None:
                    return {}
                return {
                    "model_version_id": row.model_version_id,
                    "experiment_plan_id": row.experiment_plan_id,
                }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Backtest
    # ------------------------------------------------------------------

    def _run_backtest(
        self,
        deployment_id: str | None,
        parent_run_id: str | None,
        model_version_id: str | None,
        ml_experiment_run_id: str | None,
    ) -> dict[str, Any]:
        from aqp.backtest.runner import run_backtest_from_config

        merged_cfg = self._merge_strategy_with_deployment(deployment_id)
        cfg = {
            "strategy": merged_cfg,
            "backtest": self.backtest_cfg,
        }
        # Stash linkage hints on the strategy_cfg so the runner can stamp the
        # FKs on the resulting BacktestRun row (see runner._persist_run).
        if model_version_id or ml_experiment_run_id:
            kwargs = merged_cfg.setdefault("kwargs", {})
            linkage = kwargs.setdefault("ml_linkage", {})
            if model_version_id:
                linkage["model_version_id"] = model_version_id
            if ml_experiment_run_id:
                linkage["ml_experiment_run_id"] = ml_experiment_run_id
            if self.lineage.get("experiment_plan_id"):
                linkage["experiment_plan_id"] = self.lineage["experiment_plan_id"]
            if deployment_id:
                linkage["model_deployment_id"] = deployment_id
        out = run_backtest_from_config(
            cfg,
            run_name=f"{self.run_name}/backtest",
            persist=self.persist,
            mlflow_log=True,
            strategy_id=self.lineage.get("strategy_id"),
        )
        timeline = self._fetch_timeline(out.get("run_id"))
        metrics = compute_trading_metrics(out, equity_curve=None)
        # Always include the raw runner outputs we care about.
        for key in ("sharpe", "sortino", "max_drawdown", "total_return", "final_equity"):
            if key in out and out[key] is not None:
                metrics.setdefault(key, float(out[key]))
        return {
            "backtest_run_id": out.get("run_id"),
            "metrics": metrics,
            "timeline": timeline,
            "summary": out,
        }

    def _merge_strategy_with_deployment(
        self, deployment_id: str | None
    ) -> dict[str, Any]:
        merged = deepcopy(self.strategy_cfg)
        kwargs = merged.setdefault("kwargs", {})
        alpha = kwargs.setdefault("alpha_model", {})
        alpha.setdefault("class", "DeployedModelAlpha")
        alpha.setdefault("module_path", "aqp.strategies.ml_alphas")
        alpha_kwargs = alpha.setdefault("kwargs", {})
        if deployment_id:
            alpha_kwargs["deployment_id"] = deployment_id
        return merged

    def _fetch_timeline(self, backtest_run_id: str | None) -> dict[str, Any] | None:
        if not backtest_run_id:
            return None
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import BacktestRun

            with get_session() as session:
                row = session.get(BacktestRun, backtest_run_id)
                if row is None:
                    return None
                metrics = row.metrics or {}
                if isinstance(metrics, dict):
                    return metrics.get("timeline")
        except Exception:
            logger.debug("timeline fetch skipped", exc_info=True)
        return None

    # ------------------------------------------------------------------
    # Combined metrics + persistence
    # ------------------------------------------------------------------

    def _build_combined_metrics(
        self,
        ml_metrics: dict[str, Any],
        trading_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        combined: dict[str, Any] = {
            "score": combined_score(ml_metrics, trading_metrics),
        }
        for key in (
            "sharpe",
            "sortino",
            "calmar",
            "max_drawdown",
            "total_return",
        ):
            if key in trading_metrics:
                combined[key] = trading_metrics[key]
        for key in ("ic_spearman", "icir", "hit_rate", "rmse", "mae"):
            if key in ml_metrics:
                combined[key] = ml_metrics[key]
        return combined

    def _params_snapshot(self) -> dict[str, Any]:
        return {
            "dataset_cfg": self.dataset_cfg,
            "model_cfg": self.model_cfg,
            "strategy_cfg": self.strategy_cfg,
            "backtest_cfg": self.backtest_cfg,
            "segment": self.segment,
            "train_first": self.train_first,
            "lineage": self.lineage,
        }

    def _persist_start(self, task_id: str | None) -> str | None:
        if not self.persist:
            return None
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import MLAlphaBacktestRun

            with get_session() as session:
                row = MLAlphaBacktestRun(
                    task_id=task_id,
                    run_name=self.run_name,
                    status="running",
                    experiment_plan_id=self.lineage.get("experiment_plan_id"),
                    params=self._params_snapshot(),
                    started_at=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception:
            logger.debug("MLAlphaBacktestRun start persistence skipped", exc_info=True)
            return None

    def _persist_done(self, result: AlphaBacktestResult) -> None:
        if not self.persist or not result.run_id:
            return
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import MLAlphaBacktestRun

            with get_session() as session:
                row = session.get(MLAlphaBacktestRun, result.run_id)
                if row is None:
                    return
                row.status = result.status
                row.ml_metrics = result.ml_metrics
                row.trading_metrics = result.trading_metrics
                row.combined_metrics = result.combined_metrics
                row.attribution = result.attribution
                row.error = result.error
                row.mlflow_run_id = result.mlflow_run_id
                row.ml_experiment_run_id = result.ml_experiment_run_id
                row.backtest_run_id = result.backtest_run_id
                row.model_version_id = result.model_version_id
                row.model_deployment_id = result.model_deployment_id
                row.completed_at = datetime.utcnow()
                session.add(row)
        except Exception:
            logger.debug("MLAlphaBacktestRun completion persistence skipped", exc_info=True)

    def _persist_predictions(
        self, run_id: str, timeline: dict[str, Any] | None
    ) -> None:
        if not getattr(settings, "ml_prediction_audit_enabled", False):
            return
        if self._predictions is None or self._predictions.empty:
            return
        max_rows = int(getattr(settings, "ml_prediction_audit_max_rows", 1000))
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import MLPredictionAudit

            preds = self._predictions
            if isinstance(preds.index, pd.MultiIndex):
                frame = preds.rename("prediction").reset_index()
                ts_col = next(
                    (c for c in ("ts", "timestamp", "datetime", "date") if c in frame.columns),
                    None,
                )
                sym_col = next(
                    (c for c in ("vt_symbol", "symbol", "ticker", "instrument") if c in frame.columns),
                    None,
                )
            else:
                frame = preds.rename("prediction").reset_index()
                ts_col = next(
                    (c for c in frame.columns if str(c).lower() in {"ts", "timestamp", "datetime", "date"}),
                    None,
                )
                sym_col = next(
                    (c for c in frame.columns if str(c).lower() in {"vt_symbol", "symbol", "ticker"}),
                    None,
                )

            if ts_col is None:
                return
            frame = frame.head(max_rows)
            with get_session() as session:
                for _, prediction_row in frame.iterrows():
                    try:
                        ts = pd.Timestamp(prediction_row[ts_col])
                    except Exception:
                        continue
                    session.add(
                        MLPredictionAudit(
                            alpha_backtest_run_id=run_id,
                            vt_symbol=str(prediction_row[sym_col]) if sym_col else "ALL",
                            ts=ts.to_pydatetime(),
                            prediction=float(prediction_row["prediction"]),
                            label=None,
                            position_after=None,
                            pnl_after_bar=None,
                        )
                    )
        except Exception:
            logger.debug("Prediction audit persistence skipped", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers (mirror aqp.ml.experiments — kept local to avoid import churn)
# ---------------------------------------------------------------------------


def _label_for(dataset: Any, segment: str) -> pd.Series:
    raw = dataset.prepare(segment, col_set="label")
    if isinstance(raw, pd.Series):
        return raw.astype(float)
    if isinstance(raw, pd.DataFrame):
        if isinstance(raw.columns, pd.MultiIndex) and "label" in raw.columns.get_level_values(0):
            raw = raw["label"]
        return raw.iloc[:, 0].astype(float)
    raise TypeError("dataset label segment did not resolve to a Series/DataFrame")


def _prediction_sample(pred: pd.Series, label: pd.Series | None = None) -> pd.DataFrame:
    frame = pred.rename("score").reset_index()
    if label is not None:
        try:
            label_frame = label.rename("label").reset_index()
            frame = frame.merge(label_frame, how="left")
        except Exception:
            pass
    for col in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[col]):
            frame[col] = frame[col].astype(str)
    return frame.head(500)


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
    if ".tensorflow" in module:
        return "tensorflow"
    if ".huggingface" in module:
        return "transformers"
    if ".torch" in module:
        return "pytorch"
    if ".tree" in module:
        return "gbdt"
    return None


__all__ = [
    "AlphaBacktestExperiment",
    "AlphaBacktestResult",
]
