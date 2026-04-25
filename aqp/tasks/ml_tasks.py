"""Celery tasks for native ML training + evaluation.

``train_ml_model`` materialises a ``DatasetH`` / ``TSDatasetH``, fits the
requested :class:`aqp.ml.base.Model`, runs Record templates (signal /
signal analysis / portfolio analysis), and ties the MLflow run id back
onto the optional ``Strategy`` row so the Strategy Browser can deep-link
into the full experiment.
"""
from __future__ import annotations

import hashlib
import contextlib
import logging
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.ml_tasks.train_ml_model")
def train_ml_model(
    self,
    dataset_cfg: dict[str, Any],
    model_cfg: dict[str, Any],
    run_name: str = "ml-train",
    strategy_id: str | None = None,
    records: list[dict[str, Any]] | None = None,
    register_alpha: bool = True,
    experiment_plan_id: str | None = None,
    split_plan_id: str | None = None,
    pipeline_recipe_id: str | None = None,
    dataset_version_id: str | None = None,
    split_fold: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Building dataset + model ({model_cfg.get('class')})…")

    try:
        from aqp.core.registry import build_from_config
        from aqp.mlops.mlflow_client import (
            ensure_experiment,
            experiment_name_for_strategy,
            log_alpha_training,
        )
        from aqp.mlops.model_registry import register_alpha as _register_alpha
        from aqp.persistence.db import get_session
        from aqp.persistence.models import ExperimentPlan, ModelVersion

        dataset_cfg, model_cfg, lineage = _resolve_training_inputs(
            dataset_cfg=dataset_cfg,
            model_cfg=model_cfg,
            experiment_plan_id=experiment_plan_id,
            split_plan_id=split_plan_id,
            pipeline_recipe_id=pipeline_recipe_id,
            dataset_version_id=dataset_version_id,
            split_fold=split_fold,
        )

        dataset = build_from_config(dataset_cfg)
        if dataset is None:
            raise ValueError("dataset_cfg did not resolve to an object")
        model = build_from_config(model_cfg)
        if model is None or not hasattr(model, "fit"):
            raise ValueError("model_cfg did not resolve to a Model with fit()/predict()")

        ensure_experiment(experiment_name_for_strategy(strategy_id))

        emit(task_id, "running", "Fitting model (this can take a while)…")
        model.fit(dataset)

        # Run registered Record templates (SignalRecord, SigAnaRecord, ...).
        record_summary: dict[str, dict[str, Any]] = {}
        try:
            from aqp.ml.recorder import SignalRecord

            sig = SignalRecord(model=model, dataset=dataset)
            sig_result = sig.generate()
            record_summary["SignalRecord"] = sig_result
            for rec_cfg in records or []:
                try:
                    tpl = build_from_config({**rec_cfg, "kwargs": {**rec_cfg.get("kwargs", {}), "signal_record": sig}})
                    if tpl is None:
                        continue
                    record_summary[rec_cfg["class"]] = tpl.generate()
                except Exception:
                    logger.exception("record template %s failed", rec_cfg.get("class"))
        except Exception:
            logger.exception("SignalRecord failed")

        metrics = {k: v for k, v in record_summary.get("SigAnaRecord", {}).items() if isinstance(v, (int, float))}
        hyperparams = {k: v for k, v in (model_cfg.get("kwargs", {}) or {}).items()}
        dataset_hash = lineage.get("dataset_hash") or _dataset_hash_from_dataset(dataset)
        mlflow_run_id = log_alpha_training(
            alpha_class=str(model_cfg.get("class")),
            hyperparams={**hyperparams, **lineage},
            metrics=metrics,
        )
        record_summary["mlflow_run_id"] = mlflow_run_id

        registry_name = f"{model_cfg.get('class', 'Model')}-{run_name}"
        if register_alpha:
            with tempfile.TemporaryDirectory() as tmp:
                pkl = Path(tmp) / f"{registry_name}.pkl"
                with contextlib.suppress(Exception):
                    model.to_pickle(pkl)
                    _register_alpha(
                        name=registry_name,
                        alpha_path=pkl,
                        metrics=metrics,
                        meta={
                            "strategy_id": strategy_id,
                            "dataset_class": dataset_cfg.get("class"),
                            "model_class": model_cfg.get("class"),
                            "dataset_hash": dataset_hash,
                            **lineage,
                        },
                    )

        # Persist a ModelVersion row so /ml/models lists the training.
        try:
            with get_session() as session:
                row = ModelVersion(
                    registry_name=registry_name,
                    mlflow_version=mlflow_run_id or "local",
                    stage="None",
                    dataset_hash=dataset_hash,
                    algo=str(model_cfg.get("class")),
                    dataset_version_id=lineage.get("dataset_version_id"),
                    split_plan_id=lineage.get("split_plan_id"),
                    pipeline_recipe_id=lineage.get("pipeline_recipe_id"),
                    experiment_plan_id=lineage.get("experiment_plan_id"),
                    metrics={**record_summary, "lineage": lineage},
                    created_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
                registry_id = row.id
        except Exception:
            logger.warning("ModelVersion persistence skipped", exc_info=True)
            registry_id = None

        if lineage.get("experiment_plan_id"):
            try:
                with get_session() as session:
                    plan = session.get(ExperimentPlan, lineage["experiment_plan_id"])
                    if plan is not None:
                        plan.status = "completed"
                        plan.last_run_id = mlflow_run_id or task_id
                        session.add(plan)
            except Exception:
                logger.debug("could not update experiment plan status", exc_info=True)

        result = {
            "run_name": run_name,
            "task_id": task_id,
            "mlflow_run_id": mlflow_run_id,
            "model_id": registry_id,
            "model_class": model_cfg.get("class"),
            "strategy_id": strategy_id,
            "lineage": lineage,
            "records": record_summary,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:
        logger.exception("train_ml_model failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ml_tasks.evaluate_ml_model")
def evaluate_ml_model(
    self,
    registry_name: str,
    dataset_cfg: dict[str, Any],
    strategy_id: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Evaluating model {registry_name}…")
    try:
        from aqp.core.registry import build_from_config
        from aqp.ml.base import Serializable
        from aqp.mlops.mlflow_client import ensure_experiment, experiment_name_for_strategy
        from aqp.mlops.model_registry import load_alpha_path

        path = load_alpha_path(registry_name)
        if not path:
            raise RuntimeError(f"registry has no artifact for '{registry_name}'")
        model = Serializable.from_pickle(path)

        ensure_experiment(experiment_name_for_strategy(strategy_id))
        dataset = build_from_config(dataset_cfg)

        from aqp.ml.recorder import SigAnaRecord, SignalRecord

        sig = SignalRecord(model=model, dataset=dataset)
        sig.generate()
        ana = SigAnaRecord(signal_record=sig)
        summary = ana.generate()

        result = {
            "registry_name": registry_name,
            "task_id": task_id,
            "summary": summary,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:
        logger.exception("evaluate_ml_model failed")
        emit_error(task_id, str(e))
        raise


def _resolve_training_inputs(
    *,
    dataset_cfg: dict[str, Any] | None,
    model_cfg: dict[str, Any] | None,
    experiment_plan_id: str | None,
    split_plan_id: str | None,
    pipeline_recipe_id: str | None,
    dataset_version_id: str | None,
    split_fold: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Merge explicit configs with persisted plan objects."""
    from sqlalchemy import select

    from aqp.ml.planning import artifacts_to_segments
    from aqp.persistence.db import get_session
    from aqp.persistence.models import (
        DatasetVersion,
        ExperimentPlan,
        PipelineRecipe,
        SplitArtifact,
        SplitPlan,
    )

    resolved_dataset_cfg = deepcopy(dataset_cfg or {})
    resolved_model_cfg = deepcopy(model_cfg or {})
    lineage: dict[str, Any] = {
        "experiment_plan_id": experiment_plan_id,
        "split_plan_id": split_plan_id,
        "pipeline_recipe_id": pipeline_recipe_id,
        "dataset_version_id": dataset_version_id,
        "split_fold": split_fold or "default",
    }

    with get_session() as session:
        if experiment_plan_id:
            plan = session.get(ExperimentPlan, experiment_plan_id)
            if plan is None:
                raise ValueError(f"experiment plan {experiment_plan_id!r} not found")
            if not resolved_dataset_cfg:
                resolved_dataset_cfg = deepcopy(plan.dataset_cfg or {})
            if not resolved_model_cfg:
                resolved_model_cfg = deepcopy(plan.model_cfg or {})
            split_plan_id = split_plan_id or plan.split_plan_id
            pipeline_recipe_id = pipeline_recipe_id or plan.pipeline_recipe_id
            dataset_version_id = dataset_version_id or plan.dataset_version_id
            lineage["experiment_plan_id"] = plan.id
            if plan.status in {"draft", "planned"}:
                plan.status = "running"
                session.add(plan)

        if not resolved_dataset_cfg:
            raise ValueError("dataset_cfg is required (directly or via experiment plan)")
        if not resolved_model_cfg:
            raise ValueError("model_cfg is required (directly or via experiment plan)")

        if split_plan_id:
            split_plan = session.get(SplitPlan, split_plan_id)
            if split_plan is None:
                raise ValueError(f"split plan {split_plan_id!r} not found")
            fold = split_fold or "default"
            rows = session.execute(
                select(SplitArtifact)
                .where(SplitArtifact.split_plan_id == split_plan_id)
                .where(SplitArtifact.fold_name == fold)
            ).scalars().all()
            if not rows and fold != "default":
                rows = session.execute(
                    select(SplitArtifact).where(SplitArtifact.split_plan_id == split_plan_id)
                ).scalars().all()
                fold = "default"
            artifacts = [
                {
                    "fold_name": row.fold_name,
                    "segment": row.segment,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "indices": row.indices or [],
                    "meta": row.meta or {},
                }
                for row in rows
            ]
            segments = artifacts_to_segments(artifacts, fold_name=fold)
            if segments:
                resolved_dataset_cfg.setdefault("kwargs", {})["segments"] = segments
            lineage["split_plan_id"] = split_plan_id
            lineage["split_fold"] = fold

        if pipeline_recipe_id:
            recipe = session.get(PipelineRecipe, pipeline_recipe_id)
            if recipe is None:
                raise ValueError(f"pipeline recipe {pipeline_recipe_id!r} not found")
            _inject_pipeline_recipe(resolved_dataset_cfg, recipe)
            lineage["pipeline_recipe_id"] = pipeline_recipe_id

        if dataset_version_id:
            dataset_version = session.get(DatasetVersion, dataset_version_id)
            if dataset_version is None:
                raise ValueError(f"dataset version {dataset_version_id!r} not found")
            lineage["dataset_version_id"] = dataset_version.id
            lineage["dataset_hash"] = dataset_version.dataset_hash
            if not resolved_dataset_cfg.get("kwargs", {}).get("segments"):
                inferred_segments = _segments_from_dataset_version(dataset_version)
                if inferred_segments:
                    resolved_dataset_cfg.setdefault("kwargs", {})["segments"] = inferred_segments

    # Prune nulls for compact lineage payloads.
    return (
        resolved_dataset_cfg,
        resolved_model_cfg,
        {k: v for k, v in lineage.items() if v is not None},
    )


def _inject_pipeline_recipe(dataset_cfg: dict[str, Any], recipe: Any) -> None:
    kwargs = dataset_cfg.setdefault("kwargs", {})
    handler_cfg = kwargs.get("handler")
    if not isinstance(handler_cfg, dict):
        return
    handler_kwargs = handler_cfg.setdefault("kwargs", {})
    if recipe.shared_processors:
        handler_kwargs["shared_processors"] = deepcopy(recipe.shared_processors)
    if recipe.infer_processors:
        handler_kwargs["infer_processors"] = deepcopy(recipe.infer_processors)
    if recipe.learn_processors:
        handler_kwargs["learn_processors"] = deepcopy(recipe.learn_processors)
    fit_window = dict(recipe.fit_window or {})
    if fit_window.get("fit_start_time"):
        handler_kwargs["fit_start_time"] = fit_window["fit_start_time"]
    if fit_window.get("fit_end_time"):
        handler_kwargs["fit_end_time"] = fit_window["fit_end_time"]


def _segments_from_dataset_version(dataset_version: Any) -> dict[str, list[str]]:
    if not dataset_version.start_time or not dataset_version.end_time:
        return {}
    start = pd.Timestamp(dataset_version.start_time)
    end = pd.Timestamp(dataset_version.end_time)
    midpoint = start + (end - start) * 0.7
    valid_end = start + (end - start) * 0.85
    segments = {
        "train": [start.isoformat(), midpoint.isoformat()],
        "valid": [midpoint.isoformat(), valid_end.isoformat()],
        "test": [valid_end.isoformat(), end.isoformat()],
    }
    segments["infer"] = list(segments["test"])
    return segments


def _dataset_hash_from_dataset(dataset: Any) -> str | None:
    frames: list[pd.DataFrame] = []
    for segment in ("train", "valid", "test"):
        try:
            frame = dataset.prepare(segment)
        except Exception:
            continue
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame.reset_index(drop=True))
    if not frames:
        return None
    merged = pd.concat(frames, ignore_index=True)
    payload = pd.util.hash_pandas_object(merged, index=False).values.tobytes()
    return hashlib.sha256(payload).hexdigest()
