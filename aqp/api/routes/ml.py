"""ML training / evaluation API.

Endpoints:

- ``POST /ml/train`` — launch a Celery task that builds a Dataset + Model,
  calls ``fit()``, runs the configured Record templates, and registers the
  resulting artifact.
- ``POST /ml/evaluate`` — re-run analysis on a previously-registered model.
- ``GET  /ml/models`` — list persisted :class:`ModelVersion` rows.
- ``GET  /ml/models/{id}`` — single model detail with metrics.
- ``GET  /ml/registered`` — enumerate every registered :class:`Model` class
  in the registry (handy for dropdowns in the UI).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.core.types import Symbol
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.ml.planning import build_split_plan
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    DatasetVersion,
    ExperimentPlan,
    ModelDeployment,
    ModelVersion,
    PipelineRecipe,
    SplitArtifact,
    SplitPlan,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ml", tags=["ml"])


class TrainRequest(BaseModel):
    dataset_cfg: dict[str, Any] = Field(default_factory=dict)
    model_cfg: dict[str, Any] = Field(default_factory=dict)
    run_name: str = Field(default="ml-train")
    strategy_id: str | None = None
    records: list[dict[str, Any]] | None = None
    register_alpha: bool = True
    experiment_plan_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    dataset_version_id: str | None = None
    split_fold: str | None = None


class EvaluateRequest(BaseModel):
    registry_name: str
    dataset_cfg: dict[str, Any]
    strategy_id: str | None = None


class ModelSummary(BaseModel):
    id: str
    registry_name: str
    algo: str | None
    stage: str
    mlflow_version: str
    dataset_hash: str | None = None
    dataset_version_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    experiment_plan_id: str | None = None
    created_at: datetime
    metrics: dict[str, Any] = Field(default_factory=dict)


class SplitPlanCreateRequest(BaseModel):
    name: str
    method: str = Field(default="fixed", description="fixed | purged_kfold | walk_forward")
    config: dict[str, Any] = Field(default_factory=dict)
    vt_symbols: list[str] = Field(default_factory=list)
    interval: str = "1d"
    start: str | None = None
    end: str | None = None
    dataset_version_id: str | None = None
    description: str | None = None
    created_by: str = "ui"


class SplitArtifactSummary(BaseModel):
    fold_name: str
    segment: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    n_indices: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)


class SplitPlanSummary(BaseModel):
    id: str
    name: str
    method: str
    description: str | None = None
    dataset_version_id: str | None = None
    dataset_hash: str | None = None
    segments: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime
    artifacts: list[SplitArtifactSummary] = Field(default_factory=list)


class PipelineRecipeCreateRequest(BaseModel):
    name: str
    description: str | None = None
    shared_processors: list[dict[str, Any]] = Field(default_factory=list)
    infer_processors: list[dict[str, Any]] = Field(default_factory=list)
    learn_processors: list[dict[str, Any]] = Field(default_factory=list)
    fit_window: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_by: str = "ui"


class PipelineRecipeSummary(BaseModel):
    id: str
    name: str
    version: int
    description: str | None = None
    shared_processors: list[dict[str, Any]] = Field(default_factory=list)
    infer_processors: list[dict[str, Any]] = Field(default_factory=list)
    learn_processors: list[dict[str, Any]] = Field(default_factory=list)
    fit_window: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_by: str
    is_active: bool
    created_at: datetime


class ExperimentPlanCreateRequest(BaseModel):
    name: str
    dataset_version_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    dataset_cfg: dict[str, Any] = Field(default_factory=dict)
    model_cfg: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: str = "ui"


class ExperimentPlanSummary(BaseModel):
    id: str
    name: str
    status: str
    dataset_version_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: str
    created_at: datetime


class DeploymentCreateRequest(BaseModel):
    name: str
    model_version_id: str
    experiment_plan_id: str | None = None
    dataset_version_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    alpha_class: str = "DeployedModelAlpha"
    infer_segment: str = "infer"
    long_threshold: float = 0.001
    short_threshold: float = -0.001
    allow_short: bool = True
    top_k: int | None = None
    status: str = "staging"
    deployment_config: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class DeploymentSummary(BaseModel):
    id: str
    name: str
    status: str
    model_version_id: str
    experiment_plan_id: str | None = None
    dataset_version_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    alpha_class: str
    infer_segment: str
    long_threshold: float
    short_threshold: float
    allow_short: bool
    top_k: int | None = None
    deployment_config: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


@router.post("/train", response_model=TaskAccepted)
def train_model(req: TrainRequest) -> TaskAccepted:
    """Queue a training run on the ``ml`` Celery queue."""
    from aqp.tasks.ml_tasks import train_ml_model

    async_result = train_ml_model.delay(
        req.dataset_cfg,
        req.model_cfg,
        req.run_name,
        req.strategy_id,
        req.records,
        req.register_alpha,
        req.experiment_plan_id,
        req.split_plan_id,
        req.pipeline_recipe_id,
        req.dataset_version_id,
        req.split_fold,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.post("/evaluate", response_model=TaskAccepted)
def evaluate_model(req: EvaluateRequest) -> TaskAccepted:
    from aqp.tasks.ml_tasks import evaluate_ml_model

    async_result = evaluate_ml_model.delay(
        req.registry_name,
        req.dataset_cfg,
        req.strategy_id,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.post("/split-plans", response_model=SplitPlanSummary)
def create_split_plan(req: SplitPlanCreateRequest) -> SplitPlanSummary:
    vt_symbols = list(req.vt_symbols)
    start = _parse_dt(req.start)
    end = _parse_dt(req.end)
    dataset_hash: str | None = None

    with get_session() as session:
        if req.dataset_version_id:
            dataset_version = session.get(DatasetVersion, req.dataset_version_id)
            if dataset_version is None:
                raise HTTPException(404, "dataset version not found")
            dataset_hash = dataset_version.dataset_hash
            start = start or dataset_version.start_time or datetime(2000, 1, 1)
            end = end or dataset_version.end_time or datetime.utcnow()
            if not vt_symbols:
                vt_symbols = list((dataset_version.meta or {}).get("vt_symbols") or [])

    if not vt_symbols:
        raise HTTPException(400, "vt_symbols is required when split planning")
    start = start or datetime(2000, 1, 1)
    end = end or datetime.utcnow()

    symbols = [Symbol.parse(v) if "." in v else Symbol(ticker=v) for v in vt_symbols]
    frame = DuckDBHistoryProvider().get_bars(symbols, start=start, end=end, interval=req.interval)
    if frame.empty:
        raise HTTPException(400, "no bars found for requested split plan range")

    artifacts, segments = build_split_plan(
        frame,
        method=req.method,
        config=req.config or {},
        date_column="timestamp",
    )
    with get_session() as session:
        row = SplitPlan(
            name=req.name,
            method=req.method,
            description=req.description,
            dataset_version_id=req.dataset_version_id,
            dataset_hash=dataset_hash,
            config=req.config or {},
            segments=segments,
            created_by=req.created_by,
            created_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        for artifact in artifacts:
            session.add(
                SplitArtifact(
                    split_plan_id=row.id,
                    fold_name=artifact.fold_name,
                    segment=artifact.segment,
                    start_time=artifact.start_time,
                    end_time=artifact.end_time,
                    indices=artifact.indices,
                    meta=artifact.meta,
                )
            )
        session.flush()
        rows = session.execute(
            select(SplitArtifact).where(SplitArtifact.split_plan_id == row.id)
        ).scalars().all()
        return _split_plan_summary(row, rows)


@router.get("/split-plans", response_model=list[SplitPlanSummary])
def list_split_plans(limit: int = 100) -> list[SplitPlanSummary]:
    with get_session() as session:
        rows = session.execute(select(SplitPlan).order_by(desc(SplitPlan.created_at)).limit(limit)).scalars().all()
        out: list[SplitPlanSummary] = []
        for row in rows:
            artifacts = session.execute(
                select(SplitArtifact).where(SplitArtifact.split_plan_id == row.id)
            ).scalars().all()
            out.append(_split_plan_summary(row, artifacts))
        return out


@router.get("/split-plans/{plan_id}", response_model=SplitPlanSummary)
def get_split_plan(plan_id: str) -> SplitPlanSummary:
    with get_session() as session:
        row = session.get(SplitPlan, plan_id)
        if row is None:
            raise HTTPException(404, "split plan not found")
        artifacts = session.execute(
            select(SplitArtifact).where(SplitArtifact.split_plan_id == row.id)
        ).scalars().all()
        return _split_plan_summary(row, artifacts)


@router.post("/pipelines", response_model=PipelineRecipeSummary)
def create_pipeline(req: PipelineRecipeCreateRequest) -> PipelineRecipeSummary:
    with get_session() as session:
        current_version = (
            session.execute(
                select(PipelineRecipe)
                .where(PipelineRecipe.name == req.name)
                .order_by(desc(PipelineRecipe.version))
                .limit(1)
            ).scalar_one_or_none()
        )
        row = PipelineRecipe(
            name=req.name,
            version=(current_version.version + 1) if current_version else 1,
            description=req.description,
            shared_processors=req.shared_processors,
            infer_processors=req.infer_processors,
            learn_processors=req.learn_processors,
            fit_window=req.fit_window,
            tags=req.tags,
            created_by=req.created_by,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        return _pipeline_summary(row)


@router.get("/pipelines", response_model=list[PipelineRecipeSummary])
def list_pipelines(limit: int = 100) -> list[PipelineRecipeSummary]:
    with get_session() as session:
        rows = session.execute(
            select(PipelineRecipe).order_by(desc(PipelineRecipe.created_at)).limit(limit)
        ).scalars().all()
        return [_pipeline_summary(row) for row in rows]


@router.get("/pipelines/{pipeline_id}", response_model=PipelineRecipeSummary)
def get_pipeline(pipeline_id: str) -> PipelineRecipeSummary:
    with get_session() as session:
        row = session.get(PipelineRecipe, pipeline_id)
        if row is None:
            raise HTTPException(404, "pipeline recipe not found")
        return _pipeline_summary(row)


@router.post("/experiments", response_model=ExperimentPlanSummary)
def create_experiment_plan(req: ExperimentPlanCreateRequest) -> ExperimentPlanSummary:
    with get_session() as session:
        row = ExperimentPlan(
            name=req.name,
            status="planned",
            dataset_version_id=req.dataset_version_id,
            split_plan_id=req.split_plan_id,
            pipeline_recipe_id=req.pipeline_recipe_id,
            dataset_cfg=req.dataset_cfg,
            model_cfg=req.model_cfg,
            notes=req.notes,
            tags=req.tags,
            created_by=req.created_by,
            created_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        return _experiment_summary(row)


@router.get("/experiments", response_model=list[ExperimentPlanSummary])
def list_experiment_plans(limit: int = 100) -> list[ExperimentPlanSummary]:
    with get_session() as session:
        rows = session.execute(
            select(ExperimentPlan).order_by(desc(ExperimentPlan.created_at)).limit(limit)
        ).scalars().all()
        return [_experiment_summary(row) for row in rows]


@router.get("/experiments/{experiment_id}", response_model=ExperimentPlanSummary)
def get_experiment_plan(experiment_id: str) -> ExperimentPlanSummary:
    with get_session() as session:
        row = session.get(ExperimentPlan, experiment_id)
        if row is None:
            raise HTTPException(404, "experiment plan not found")
        return _experiment_summary(row)


@router.post("/deployments", response_model=DeploymentSummary)
def create_model_deployment(req: DeploymentCreateRequest) -> DeploymentSummary:
    with get_session() as session:
        model_row = session.get(ModelVersion, req.model_version_id)
        if model_row is None:
            raise HTTPException(404, "model version not found")
        row = ModelDeployment(
            name=req.name,
            status=req.status,
            model_version_id=req.model_version_id,
            experiment_plan_id=req.experiment_plan_id,
            dataset_version_id=req.dataset_version_id,
            split_plan_id=req.split_plan_id,
            pipeline_recipe_id=req.pipeline_recipe_id,
            alpha_class=req.alpha_class,
            infer_segment=req.infer_segment,
            long_threshold=req.long_threshold,
            short_threshold=req.short_threshold,
            allow_short=req.allow_short,
            top_k=req.top_k,
            deployment_config=req.deployment_config,
            meta=req.meta,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        return _deployment_summary(row)


@router.get("/deployments", response_model=list[DeploymentSummary])
def list_model_deployments(limit: int = 100) -> list[DeploymentSummary]:
    with get_session() as session:
        rows = session.execute(
            select(ModelDeployment).order_by(desc(ModelDeployment.created_at)).limit(limit)
        ).scalars().all()
        return [_deployment_summary(row) for row in rows]


@router.get("/deployments/{deployment_id}", response_model=DeploymentSummary)
def get_model_deployment(deployment_id: str) -> DeploymentSummary:
    with get_session() as session:
        row = session.get(ModelDeployment, deployment_id)
        if row is None:
            raise HTTPException(404, "model deployment not found")
        return _deployment_summary(row)


@router.get("/deployments/{deployment_id}/alpha-config")
def get_deployment_alpha_config(deployment_id: str) -> dict[str, Any]:
    with get_session() as session:
        row = session.get(ModelDeployment, deployment_id)
        if row is None:
            raise HTTPException(404, "model deployment not found")
        return {
            "class": row.alpha_class,
            "module_path": "aqp.strategies.ml_alphas",
            "kwargs": {
                "deployment_id": row.id,
                "long_threshold": row.long_threshold,
                "short_threshold": row.short_threshold,
                "allow_short": row.allow_short,
                "top_k": row.top_k,
                **(row.deployment_config or {}),
            },
        }


@router.get("/models", response_model=list[ModelSummary])
def list_models(limit: int = 100, registry_name: str | None = None) -> list[ModelSummary]:
    with get_session() as s:
        stmt = select(ModelVersion).order_by(desc(ModelVersion.created_at)).limit(limit)
        if registry_name:
            stmt = stmt.where(ModelVersion.registry_name == registry_name)
        rows = s.execute(stmt).scalars().all()
        return [
            ModelSummary(
                id=r.id,
                registry_name=r.registry_name,
                algo=r.algo,
                stage=r.stage,
                mlflow_version=r.mlflow_version,
                dataset_hash=r.dataset_hash,
                dataset_version_id=r.dataset_version_id,
                split_plan_id=r.split_plan_id,
                pipeline_recipe_id=r.pipeline_recipe_id,
                experiment_plan_id=r.experiment_plan_id,
                created_at=r.created_at,
                metrics=r.metrics or {},
            )
            for r in rows
        ]


@router.get("/models/{model_id}", response_model=ModelSummary)
def get_model(model_id: str) -> ModelSummary:
    with get_session() as s:
        row = s.get(ModelVersion, model_id)
        if row is None:
            raise HTTPException(404, "model version not found")
        return ModelSummary(
            id=row.id,
            registry_name=row.registry_name,
            algo=row.algo,
            stage=row.stage,
            mlflow_version=row.mlflow_version,
            dataset_hash=row.dataset_hash,
            dataset_version_id=row.dataset_version_id,
            split_plan_id=row.split_plan_id,
            pipeline_recipe_id=row.pipeline_recipe_id,
            experiment_plan_id=row.experiment_plan_id,
            created_at=row.created_at,
            metrics=row.metrics or {},
        )


@router.get("/models/{model_id}/details")
def get_model_details(model_id: str, top_k: int = 25) -> dict[str, Any]:
    """Richer per-model payload used by the ML Model Detail UI page.

    Fields:

    - ``summary`` — base :class:`ModelSummary` fields.
    - ``metrics`` — metrics dict stored on the row + any MLflow metrics we
      can retrieve via the tracking URI.
    - ``feature_importance`` — list of ``{name, importance}`` pairs when
      the registered model exposes one.
    - ``predictions`` — most recent test-set predictions with ``label`` and
      ``score`` columns (first ``top_k`` rows).
    - ``lineage`` — dataset_hash + MLflow run id for deep-linking.
    """
    with get_session() as s:
        row = s.get(ModelVersion, model_id)
        if row is None:
            raise HTTPException(404, "model version not found")
        summary = {
            "id": row.id,
            "registry_name": row.registry_name,
            "algo": row.algo,
            "stage": row.stage,
            "mlflow_version": row.mlflow_version,
            "dataset_hash": row.dataset_hash,
            "dataset_version_id": row.dataset_version_id,
            "split_plan_id": row.split_plan_id,
            "pipeline_recipe_id": row.pipeline_recipe_id,
            "experiment_plan_id": row.experiment_plan_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "metrics": row.metrics or {},
        }

    feature_importance: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    mlflow_metrics: dict[str, Any] = {}
    mlflow_run_id = summary.get("metrics", {}).get("mlflow_run_id")

    # MLflow metrics + artifacts, best-effort (no crash if server is offline).
    try:
        import mlflow

        from aqp.config import settings

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        client = mlflow.tracking.MlflowClient()
        if mlflow_run_id:
            run = client.get_run(mlflow_run_id)
            mlflow_metrics = {k: float(v) for k, v in (run.data.metrics or {}).items()}
            # Try to pull feature importance from the run's params or artifacts.
            feature_importance = _pull_feature_importance(client, run, top_k=top_k)
            predictions = _pull_predictions(client, run, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        logger.debug("MLflow lookup failed for %s: %s", model_id, exc, exc_info=True)

    return {
        "summary": summary,
        "metrics": {**(summary["metrics"] or {}), **mlflow_metrics},
        "feature_importance": feature_importance,
        "predictions": predictions,
        "lineage": {
            "dataset_hash": summary["dataset_hash"],
            "dataset_version_id": summary["dataset_version_id"],
            "split_plan_id": summary["split_plan_id"],
            "pipeline_recipe_id": summary["pipeline_recipe_id"],
            "experiment_plan_id": summary["experiment_plan_id"],
            "mlflow_run_id": mlflow_run_id,
        },
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _split_plan_summary(row: SplitPlan, artifacts: list[SplitArtifact]) -> SplitPlanSummary:
    return SplitPlanSummary(
        id=row.id,
        name=row.name,
        method=row.method,
        description=row.description,
        dataset_version_id=row.dataset_version_id,
        dataset_hash=row.dataset_hash,
        segments=row.segments or {},
        config=row.config or {},
        created_by=row.created_by,
        created_at=row.created_at,
        artifacts=[
            SplitArtifactSummary(
                fold_name=artifact.fold_name,
                segment=artifact.segment,
                start_time=artifact.start_time,
                end_time=artifact.end_time,
                n_indices=len(artifact.indices or []),
                meta=artifact.meta or {},
            )
            for artifact in artifacts
        ],
    )


def _pipeline_summary(row: PipelineRecipe) -> PipelineRecipeSummary:
    return PipelineRecipeSummary(
        id=row.id,
        name=row.name,
        version=row.version,
        description=row.description,
        shared_processors=row.shared_processors or [],
        infer_processors=row.infer_processors or [],
        learn_processors=row.learn_processors or [],
        fit_window=row.fit_window or {},
        tags=row.tags or [],
        created_by=row.created_by,
        is_active=bool(row.is_active),
        created_at=row.created_at,
    )


def _experiment_summary(row: ExperimentPlan) -> ExperimentPlanSummary:
    return ExperimentPlanSummary(
        id=row.id,
        name=row.name,
        status=row.status,
        dataset_version_id=row.dataset_version_id,
        split_plan_id=row.split_plan_id,
        pipeline_recipe_id=row.pipeline_recipe_id,
        notes=row.notes,
        tags=row.tags or [],
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _deployment_summary(row: ModelDeployment) -> DeploymentSummary:
    return DeploymentSummary(
        id=row.id,
        name=row.name,
        status=row.status,
        model_version_id=row.model_version_id,
        experiment_plan_id=row.experiment_plan_id,
        dataset_version_id=row.dataset_version_id,
        split_plan_id=row.split_plan_id,
        pipeline_recipe_id=row.pipeline_recipe_id,
        alpha_class=row.alpha_class,
        infer_segment=row.infer_segment,
        long_threshold=row.long_threshold,
        short_threshold=row.short_threshold,
        allow_short=row.allow_short,
        top_k=row.top_k,
        deployment_config=row.deployment_config or {},
        meta=row.meta or {},
        created_at=row.created_at,
    )


def _pull_feature_importance(client: Any, run: Any, *, top_k: int) -> list[dict[str, Any]]:
    """Best-effort extraction of a ``feature_importance`` artifact or param.

    Supported shapes:
    - ``feature_importance.json`` artifact → dict or list-of-dicts.
    - Params of the form ``feature_importance.<name>: <value>``.
    """
    try:
        artifact_uri = run.info.artifact_uri
        download_dir = client.download_artifacts(run.info.run_id, "feature_importance.json")
        import json as _json
        from pathlib import Path as _P

        path = _P(download_dir)
        if path.is_file():
            data = _json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return sorted(
                    (
                        {"name": k, "importance": float(v)}
                        for k, v in data.items()
                    ),
                    key=lambda r: abs(r["importance"]),
                    reverse=True,
                )[:top_k]
            if isinstance(data, list):
                return data[:top_k]
        del artifact_uri  # silence linters
    except Exception:
        pass

    params = dict((run.data.params or {}).items())
    rows: list[dict[str, Any]] = []
    for key, value in params.items():
        if key.startswith("feature_importance."):
            try:
                rows.append({"name": key.split(".", 1)[1], "importance": float(value)})
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: abs(r.get("importance", 0.0)), reverse=True)
    return rows[:top_k]


def _pull_predictions(client: Any, run: Any, *, top_k: int) -> list[dict[str, Any]]:
    """Best-effort load of a ``predictions.csv`` artifact."""
    try:
        import pandas as pd

        path = client.download_artifacts(run.info.run_id, "predictions.csv")
        from pathlib import Path as _P

        p = _P(path)
        if not p.exists():
            return []
        df = pd.read_csv(p)
        return df.head(top_k).to_dict(orient="records")
    except Exception:
        return []


@router.get("/registered")
def registered_models() -> dict[str, list[str]]:
    """Introspect registered Model classes in :mod:`aqp.ml.models`."""
    try:
        # Ensure submodules (and thus @register decorators) run.
        import aqp.ml  # noqa: F401
        import aqp.ml.models  # noqa: F401
        from aqp.core.registry import list_registered

        all_names = list_registered()
    except Exception as e:
        logger.warning("registry introspection failed: %s", e)
        return {"tree": [], "linear": [], "torch": [], "handlers": [], "datasets": []}

    buckets = {
        "tree": ["LGBModel", "XGBModel", "CatBoostModel", "DEnsembleModel"],
        "linear": ["LinearModel"],
        "torch": [
            "DNNModel",
            "LSTMModel",
            "GRUModel",
            "ALSTMModel",
            "TransformerModel",
            "TCNModel",
            "TabNetModel",
            "LocalformerModel",
            "GeneralPTNN",
            "LSTMSeq2Seq",
            "GRUSeq2Seq",
            "LSTMSeq2SeqVAE",
            "DilatedCNNSeq2Seq",
            "TransformerForecaster",
        ],
        "torch_tier_b": [
            "GATsModel", "HISTModel", "TRAModel", "ADDModel", "ADARNNModel",
            "TCTSModel", "SFMModel", "SandwichModel", "KRNNModel", "IGMTFModel",
        ],
        "handlers": ["Alpha158", "Alpha360"],
        "datasets": ["DatasetH", "TSDatasetH"],
    }
    # Filter against the actual registry so missing installs (torch, etc.)
    # don't claim a model exists.
    available = set(all_names)
    return {k: [n for n in v if n in available] for k, v in buckets.items()}
