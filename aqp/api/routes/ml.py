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

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.config import settings
from aqp.core.types import Symbol
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.ml.planning import build_split_plan
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    DatasetVersion,
    ExperimentPlan,
    MLExperimentRun,
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


class ExperimentRunRequest(BaseModel):
    dataset_cfg: dict[str, Any] = Field(default_factory=dict)
    model_cfg: dict[str, Any] = Field(default_factory=dict)
    run_name: str = "ml-experiment"
    experiment_type: str = Field(default="alpha", description="alpha | forecast | classification | anomaly | generic")
    records: list[dict[str, Any]] | None = None
    segment: str = "test"
    experiment_plan_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    dataset_version_id: str | None = None
    split_fold: str | None = None


class ExperimentRunSummary(BaseModel):
    id: str
    task_id: str | None = None
    run_name: str
    experiment_type: str
    status: str
    framework: str | None = None
    model_class: str | None = None
    model_version_id: str | None = None
    experiment_plan_id: str | None = None
    dataset_version_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    dataset_hash: str | None = None
    mlflow_run_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    prediction_sample: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class FlowPreviewRequest(BaseModel):
    dataset_cfg: dict[str, Any] = Field(default_factory=dict)
    segment: str = "test"
    estimator: str = "ridge"
    alpha: float = 1.0
    l1_ratio: float = 0.5
    backend: str = "prophet"
    horizon: int = Field(default=20, ge=1, le=500)
    column: str | None = None
    period: int = Field(default=20, ge=2, le=500)
    forecaster_kwargs: dict[str, Any] = Field(default_factory=dict)
    # Fields used by the diagnostic / statistical flows.
    max_features: int = Field(default=20, ge=1, le=200)
    test: str = "all"
    nlags: int = Field(default=40, ge=1, le=500)
    cause_column: str | None = None
    effect_column: str | None = None
    max_lag: int = Field(default=5, ge=1, le=100)
    columns: list[str] = Field(default_factory=list)
    p: int = Field(default=1, ge=0, le=20)
    q: int = Field(default=1, ge=0, le=20)
    n_breakpoints: int = Field(default=5, ge=1, le=100)
    n_clusters: int = Field(default=4, ge=1, le=200)
    eps: float = 0.5
    min_samples: int = Field(default=5, ge=1, le=1000)
    n_components: int = Field(default=10, ge=1, le=200)


class DeploymentTestRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    last_n: int = Field(default=50, ge=1, le=500)


class AlphaBacktestRunRequest(BaseModel):
    """Request body for ``POST /ml/alpha-backtest-runs``.

    The combined ML+backtest experiment requires (at minimum) a
    ``strategy_cfg`` and ``backtest_cfg``. When ``train_first`` is true
    (default), ``dataset_cfg`` and ``model_cfg`` are also required and the
    experiment trains the model up-front. Otherwise an existing
    ``deployment_id`` must be supplied.
    """

    strategy_cfg: dict[str, Any]
    backtest_cfg: dict[str, Any]
    dataset_cfg: dict[str, Any] | None = None
    model_cfg: dict[str, Any] | None = None
    run_name: str = Field(default="alpha-backtest")
    segment: str = "test"
    train_first: bool = True
    deployment_id: str | None = None
    deployment_overrides: dict[str, Any] | None = None
    capture_predictions: bool = True
    records: list[dict[str, Any]] | None = None
    experiment_plan_id: str | None = None
    split_plan_id: str | None = None
    pipeline_recipe_id: str | None = None
    dataset_version_id: str | None = None
    split_fold: str | None = None
    strategy_id: str | None = None


class AlphaBacktestRunSummary(BaseModel):
    id: str
    run_name: str
    status: str
    task_id: str | None = None
    ml_experiment_run_id: str | None = None
    backtest_run_id: str | None = None
    model_version_id: str | None = None
    model_deployment_id: str | None = None
    experiment_plan_id: str | None = None
    mlflow_run_id: str | None = None
    dataset_hash: str | None = None
    ml_metrics: dict[str, Any] = Field(default_factory=dict)
    trading_metrics: dict[str, Any] = Field(default_factory=dict)
    combined_metrics: dict[str, Any] = Field(default_factory=dict)
    attribution: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class AlphaBacktestPredictionRow(BaseModel):
    id: str
    vt_symbol: str
    ts: datetime
    prediction: float
    label: float | None = None
    position_after: float | None = None
    pnl_after_bar: float | None = None


class TestSinglePredictRequest(BaseModel):
    deployment_id: str
    feature_row: dict[str, Any]
    vt_symbol: str | None = None
    sync: bool = True


class TestBatchPredictRequest(BaseModel):
    deployment_id: str
    symbols: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    last_n: int = Field(default=200, ge=1, le=5000)
    iceberg_identifier: str | None = None


class TestCompareRequest(BaseModel):
    deployment_id_a: str
    deployment_id_b: str
    symbols: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    last_n: int = Field(default=200, ge=1, le=5000)


class TestScenarioRequest(BaseModel):
    deployment_id: str
    feature_row: dict[str, float]
    perturbations: list[float] | None = None
    sync: bool = True


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


@router.post("/experiment-runs", response_model=TaskAccepted)
def run_experiment(req: ExperimentRunRequest) -> TaskAccepted:
    from aqp.tasks.ml_tasks import run_ml_experiment

    async_result = run_ml_experiment.delay(
        req.dataset_cfg,
        req.model_cfg,
        req.run_name,
        req.experiment_type,
        req.records,
        req.segment,
        req.experiment_plan_id,
        req.split_plan_id,
        req.pipeline_recipe_id,
        req.dataset_version_id,
        req.split_fold,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/experiment-runs", response_model=list[ExperimentRunSummary])
def list_experiment_runs(limit: int = 100) -> list[ExperimentRunSummary]:
    with get_session() as session:
        rows = session.execute(
            select(MLExperimentRun).order_by(desc(MLExperimentRun.started_at)).limit(limit)
        ).scalars().all()
        return [_experiment_run_summary(row) for row in rows]


@router.post("/alpha-backtest-runs", response_model=TaskAccepted)
def run_alpha_backtest(req: AlphaBacktestRunRequest) -> TaskAccepted:
    """Queue a combined ML + backtest experiment on the ``ml`` Celery queue.

    Drives :class:`aqp.ml.alpha_backtest_experiment.AlphaBacktestExperiment`
    end-to-end: trains the model, registers a ``ModelVersion``, optionally
    provisions a ``ModelDeployment``, runs the backtest with the new model
    wired in as the alpha source, and persists a ``MLAlphaBacktestRun``
    that links everything together.
    """
    if req.train_first:
        if not req.dataset_cfg or not req.model_cfg:
            raise HTTPException(
                400,
                "train_first=true requires both dataset_cfg and model_cfg",
            )
    else:
        if not req.deployment_id:
            raise HTTPException(
                400, "train_first=false requires an existing deployment_id"
            )
    from aqp.tasks.ml_tasks import run_alpha_backtest_experiment

    async_result = run_alpha_backtest_experiment.delay(
        strategy_cfg=req.strategy_cfg,
        backtest_cfg=req.backtest_cfg,
        dataset_cfg=req.dataset_cfg or {},
        model_cfg=req.model_cfg or {},
        run_name=req.run_name,
        segment=req.segment,
        train_first=req.train_first,
        deployment_id=req.deployment_id,
        deployment_overrides=req.deployment_overrides,
        capture_predictions=req.capture_predictions,
        records=req.records,
        experiment_plan_id=req.experiment_plan_id,
        split_plan_id=req.split_plan_id,
        pipeline_recipe_id=req.pipeline_recipe_id,
        dataset_version_id=req.dataset_version_id,
        split_fold=req.split_fold,
        strategy_id=req.strategy_id,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/alpha-backtest-runs", response_model=list[AlphaBacktestRunSummary])
def list_alpha_backtest_runs(limit: int = 100) -> list[AlphaBacktestRunSummary]:
    from aqp.persistence.models import MLAlphaBacktestRun

    with get_session() as session:
        rows = (
            session.execute(
                select(MLAlphaBacktestRun)
                .order_by(desc(MLAlphaBacktestRun.started_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_alpha_backtest_run_summary(row) for row in rows]


@router.get(
    "/alpha-backtest-runs/{run_id}", response_model=AlphaBacktestRunSummary
)
def get_alpha_backtest_run(run_id: str) -> AlphaBacktestRunSummary:
    from aqp.persistence.models import MLAlphaBacktestRun

    with get_session() as session:
        row = session.get(MLAlphaBacktestRun, run_id)
        if row is None:
            raise HTTPException(404, "alpha backtest run not found")
        return _alpha_backtest_run_summary(row)


@router.get(
    "/alpha-backtest-runs/{run_id}/predictions",
    response_model=list[AlphaBacktestPredictionRow],
)
def list_alpha_backtest_predictions(
    run_id: str, limit: int = 500, vt_symbol: str | None = None
) -> list[AlphaBacktestPredictionRow]:
    from aqp.persistence.models import MLPredictionAudit

    with get_session() as session:
        stmt = (
            select(MLPredictionAudit)
            .where(MLPredictionAudit.alpha_backtest_run_id == run_id)
            .order_by(MLPredictionAudit.ts)
            .limit(int(limit))
        )
        if vt_symbol:
            stmt = stmt.where(MLPredictionAudit.vt_symbol == vt_symbol)
        rows = session.execute(stmt).scalars().all()
        return [
            AlphaBacktestPredictionRow(
                id=str(row.id),
                vt_symbol=row.vt_symbol,
                ts=row.ts,
                prediction=float(row.prediction),
                label=float(row.label) if row.label is not None else None,
                position_after=(
                    float(row.position_after) if row.position_after is not None else None
                ),
                pnl_after_bar=(
                    float(row.pnl_after_bar) if row.pnl_after_bar is not None else None
                ),
            )
            for row in rows
        ]


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


@router.post("/deployments/{deployment_id}/test", response_model=TaskAccepted)
def test_model_deployment(deployment_id: str, req: DeploymentTestRequest) -> TaskAccepted:
    from aqp.tasks.ml_tasks import test_ml_deployment

    async_result = test_ml_deployment.delay(
        deployment_id,
        req.symbols,
        req.start,
        req.end,
        req.last_n,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


class DeploymentPreviewRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    last_n: int = Field(default=20, ge=1, le=200)


@router.post("/deployments/{deployment_id}/preview")
def preview_deployment(
    deployment_id: str, req: DeploymentPreviewRequest
) -> dict[str, Any]:
    """Run the deployment's alpha on a small slice of bars and return last-N predictions.

    Used by the backtest wizard's ML-alpha preview card. Failures are
    returned as a structured error payload instead of HTTP 500 so the UI
    can render them gracefully.
    """
    import pandas as pd

    with get_session() as session:
        row = session.get(ModelDeployment, deployment_id)
        if row is None:
            raise HTTPException(404, "model deployment not found")

    symbols = [s.strip() for s in (req.symbols or []) if s.strip()] or settings.universe_list
    if not symbols:
        return {"error": "no symbols provided", "n_signals": 0, "signals": []}

    parsed_symbols = [Symbol.parse(s) if "." in s else Symbol(ticker=s) for s in symbols]
    start_ts = pd.Timestamp(req.start or settings.default_start)
    end_ts = pd.Timestamp(req.end or settings.default_end)

    try:
        provider = DuckDBHistoryProvider()
        bars = provider.get_bars(parsed_symbols, start=start_ts, end=end_ts)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"could not load bars: {exc}", "n_signals": 0, "signals": []}

    if bars.empty:
        return {
            "error": "no bars in window",
            "n_signals": 0,
            "signals": [],
            "start": str(start_ts.date()),
            "end": str(end_ts.date()),
        }

    try:
        from aqp.strategies.ml_alphas import DeployedModelAlpha

        alpha = DeployedModelAlpha(deployment_id=deployment_id)
        signals = alpha.generate_signals(
            bars=bars,
            universe=parsed_symbols,
            context={"current_time": end_ts},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("deployment preview failed")
        return {
            "error": f"alpha inference failed: {exc}",
            "n_signals": 0,
            "signals": [],
        }

    out = [
        {
            "vt_symbol": str(sig.symbol.vt_symbol),
            "direction": sig.direction.value if hasattr(sig.direction, "value") else str(sig.direction),
            "strength": float(sig.strength),
            "confidence": float(sig.confidence),
            "timestamp": str(sig.timestamp),
            "rationale": sig.rationale,
        }
        for sig in signals[: req.last_n]
    ]
    return {
        "deployment_id": deployment_id,
        "n_signals": len(signals),
        "signals": out,
        "start": str(start_ts.date()),
        "end": str(end_ts.date()),
        "n_symbols": len(parsed_symbols),
        "n_bars": int(len(bars)),
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


def _experiment_run_summary(row: MLExperimentRun) -> ExperimentRunSummary:
    return ExperimentRunSummary(
        id=row.id,
        task_id=row.task_id,
        run_name=row.run_name,
        experiment_type=row.experiment_type,
        status=row.status,
        framework=row.framework,
        model_class=row.model_class,
        model_version_id=row.model_version_id,
        experiment_plan_id=row.experiment_plan_id,
        dataset_version_id=row.dataset_version_id,
        split_plan_id=row.split_plan_id,
        pipeline_recipe_id=row.pipeline_recipe_id,
        dataset_hash=row.dataset_hash,
        mlflow_run_id=row.mlflow_run_id,
        metrics=row.metrics or {},
        prediction_sample=row.prediction_sample or [],
        error=row.error,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _alpha_backtest_run_summary(row: Any) -> AlphaBacktestRunSummary:
    return AlphaBacktestRunSummary(
        id=str(row.id),
        run_name=row.run_name,
        status=row.status,
        task_id=row.task_id,
        ml_experiment_run_id=row.ml_experiment_run_id,
        backtest_run_id=row.backtest_run_id,
        model_version_id=row.model_version_id,
        model_deployment_id=row.model_deployment_id,
        experiment_plan_id=row.experiment_plan_id,
        mlflow_run_id=row.mlflow_run_id,
        dataset_hash=row.dataset_hash,
        ml_metrics=row.ml_metrics or {},
        trading_metrics=row.trading_metrics or {},
        combined_metrics=row.combined_metrics or {},
        attribution=row.attribution or {},
        error=row.error,
        started_at=row.started_at,
        completed_at=row.completed_at,
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
        "tree": [
            "LGBModel", "XGBModel", "CatBoostModel", "DEnsembleModel", "HighFreqGBDT",
        ],
        "linear": ["LinearModel"],
        "sklearn": ["SklearnRegressorModel", "SklearnClassifierModel", "SklearnPipelineModel"],
        "forecasting": ["ProphetForecastModel", "SktimeForecastModel", "SktimeReductionForecastModel"],
        "anomaly": ["PyODAnomalyModel"],
        "keras": ["KerasMLPModel", "KerasLSTMModel"],
        "transformers": ["HuggingFaceTextSignalModel"],
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
        "torch_ts": [
            "LSTMTSModel", "GRUTSModel", "ALSTMTSModel", "TCNTSModel",
            "LocalformerTSModel", "TransformerTSModel", "GATsTSModel",
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


# ---------------------------------------------------------------------------
# Processor catalog (Pipeline tab in the UI).
# ---------------------------------------------------------------------------


_PROCESSOR_CATALOG: list[dict[str, Any]] = [
    {
        "name": "Fillna",
        "kind": "null",
        "description": "Fill NaN values with a constant or strategy (ffill / bfill / mean / 0).",
        "params": [
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "fill_value", "default": 0.0, "type": "float|str", "description": "Number, 'ffill', 'bfill', or 'mean'"},
        ],
    },
    {
        "name": "DropnaLabel",
        "kind": "null",
        "description": "Drop rows whose label column is NaN.",
        "params": [{"name": "fields_group", "default": "label", "type": "str"}],
    },
    {
        "name": "FilterCol",
        "kind": "filter",
        "description": "Keep only columns whose last-level name is in `col_list`.",
        "params": [
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "col_list", "default": [], "type": "list[str]"},
        ],
    },
    {
        "name": "CSZScoreNorm",
        "kind": "normalize",
        "description": "Cross-sectional z-score per timestamp.",
        "params": [{"name": "fields_group", "default": "feature", "type": "str"}],
    },
    {
        "name": "CSRankNorm",
        "kind": "normalize",
        "description": "Cross-sectional rank to [-1, 1] per timestamp.",
        "params": [{"name": "fields_group", "default": "feature", "type": "str"}],
    },
    {
        "name": "MinMaxNorm",
        "kind": "normalize",
        "description": "Fit-stateful min/max rescaling to [0, 1] per column.",
        "params": [{"name": "fields_group", "default": "feature", "type": "str"}],
    },
    {
        "name": "RobustScaler",
        "kind": "normalize",
        "description": "Outlier-resistant (x - median) / IQR scaling.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "quantile_range", "default": [0.25, 0.75], "type": "list[float]"},
        ],
    },
    {
        "name": "OneHotEncode",
        "kind": "categorical",
        "description": "One-hot encode low-cardinality categorical columns.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "drop_first", "default": True, "type": "bool"},
            {"name": "max_cardinality", "default": 64, "type": "int"},
        ],
    },
    {
        "name": "OrdinalEncode",
        "kind": "categorical",
        "description": "Map categories to integer codes (explicit or fit-time).",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "mapping", "default": None, "type": "dict[str,dict]"},
            {"name": "unknown_value", "default": -1, "type": "int"},
        ],
    },
    {
        "name": "TargetEncode",
        "kind": "categorical",
        "description": "Smoothed target (label-mean) encoding for categoricals.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "label_column", "default": "label", "type": "str"},
            {"name": "smoothing", "default": 10.0, "type": "float"},
        ],
    },
    {
        "name": "HashEncode",
        "kind": "categorical",
        "description": "Stateless feature-hashing for high-cardinality columns.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "n_features", "default": 64, "type": "int"},
        ],
    },
    {
        "name": "FrequencyEncode",
        "kind": "categorical",
        "description": "Replace categories with their training-set frequency.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "fields_group", "default": "feature", "type": "str"},
        ],
    },
    {
        "name": "PyODOutlierFilter",
        "kind": "outlier",
        "description": "Drop or flag outliers via PyOD detectors (iforest/knn/ecod/copod/lof).",
        "params": [
            {"name": "detector", "default": "iforest", "type": "str"},
            {"name": "fields_group", "default": "feature", "type": "str"},
            {"name": "contamination", "default": 0.02, "type": "float"},
            {"name": "drop", "default": True, "type": "bool"},
        ],
    },
    {
        "name": "SklearnTransformerProcessor",
        "kind": "normalize",
        "description": "Apply a fit-stateful sklearn transformer to feature columns.",
        "params": [
            {"name": "transformer", "default": "standard_scaler", "type": "str"},
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "fields_group", "default": "feature", "type": "str"},
        ],
    },
    {
        "name": "LagFeatureGenerator",
        "kind": "feature",
        "description": "Add per-symbol lag features for selected numeric columns.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "lags", "default": [1, 5, 10], "type": "list[int]"},
        ],
    },
    {
        "name": "RollingFeatureGenerator",
        "kind": "feature",
        "description": "Add rolling mean/std/min/max features per symbol.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "windows", "default": [5, 20], "type": "list[int]"},
            {"name": "stats", "default": ["mean", "std"], "type": "list[str]"},
        ],
    },
    {
        "name": "SeasonalDecomposeFeatures",
        "kind": "feature",
        "description": "Add STL trend/seasonal/residual components for selected columns.",
        "params": [
            {"name": "columns", "default": [], "type": "list[str]"},
            {"name": "period", "default": 20, "type": "int"},
        ],
    },
]


@router.get("/processors")
def list_processors() -> list[dict[str, Any]]:
    """Return the catalog of preprocessing classes available to the UI."""
    return _PROCESSOR_CATALOG


@router.post("/pipelines/validate")
def validate_pipeline_recipe(req: PipelineRecipeCreateRequest) -> dict[str, Any]:
    from aqp.ml.pipeline_recipes import validate_recipe

    return validate_recipe(
        {
            "shared_processors": req.shared_processors,
            "infer_processors": req.infer_processors,
            "learn_processors": req.learn_processors,
            "fit_window": req.fit_window,
        }
    )


class PipelineExportRequest(BaseModel):
    output_topic: str = Field(default="features.signals.v1")
    parallelism: int = Field(default=1, ge=1, le=16)


@router.post("/pipelines/{pipeline_id}/export")
def export_pipeline_to_kafka(pipeline_id: str, req: PipelineExportRequest | None = None) -> dict[str, Any]:
    """Compile a saved pipeline recipe into a Flink/Kafka job spec.

    Best-effort: when the streaming runtime isn't configured we still
    return the spec so the UI can render a deterministic preview.
    """
    cfg = req or PipelineExportRequest()
    with get_session() as session:
        row = session.get(PipelineRecipe, pipeline_id)
        if row is None:
            raise HTTPException(404, "pipeline recipe not found")
        spec = {
            "job_id": f"pipeline-{row.name}-v{row.version}",
            "pipeline_id": pipeline_id,
            "name": row.name,
            "version": row.version,
            "shared_processors": list(row.shared_processors or []),
            "infer_processors": list(row.infer_processors or []),
            "learn_processors": list(row.learn_processors or []),
            "topic": cfg.output_topic,
            "parallelism": cfg.parallelism,
        }

    submitted = False
    error: str | None = None
    try:  # pragma: no cover - streaming runtime is optional
        from aqp.streaming.runtime import submit_factor_job  # type: ignore[import-not-found]

        submit_factor_job(spec)
        submitted = True
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    spec["submitted"] = submitted
    if error:
        spec["error"] = error
    return spec


@router.post("/pipelines/{pipeline_id}/as-node")
def pipeline_recipe_as_node(
    pipeline_id: str, overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Resolve a saved ``PipelineRecipe`` into a manifest ``NodeSpec`` fragment.

    Lets the Manifest Builder UI drop a saved ML preprocessing recipe
    directly onto a data pipeline canvas. Mirrors the
    ``/sinks/{sink_id}/as-node`` pattern.
    """
    from aqp.ml.pipeline_recipes import materialise_node_spec

    try:
        return materialise_node_spec(pipeline_id, overrides=overrides)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class DatasetPreviewRequest(BaseModel):
    handler_cfg: dict[str, Any] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    segments: dict[str, list[str]] = Field(default_factory=dict)
    processors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each entry: {class, module_path, kwargs} — applied in order.",
    )
    rows: int = Field(default=50, ge=5, le=500)


@router.post("/datasets/preview")
def datasets_preview(req: DatasetPreviewRequest) -> dict[str, Any]:
    """Materialize a small sample of a dataset + processors stack.

    Drives the "Pipeline" tab live preview. Best-effort: returns an
    ``error`` field instead of raising when handlers/processors fail
    so the UI can still show what was requested.
    """
    from aqp.core.registry import build_from_config

    handler_cfg = req.handler_cfg or {
        "class": "Alpha158",
        "module_path": "aqp.ml.features.alpha158",
        "kwargs": {
            "instruments": req.symbols or ["SPY", "AAPL", "MSFT"],
            "start_time": "2022-01-01",
            "end_time": "2024-06-30",
        },
    }

    out: dict[str, Any] = {
        "handler": handler_cfg,
        "rows": [],
        "columns": [],
        "n_rows": 0,
        "n_cols": 0,
        "error": None,
    }
    try:
        handler = build_from_config(handler_cfg)
        df = handler.fetch() if hasattr(handler, "fetch") else handler
        if not hasattr(df, "tail"):
            out["error"] = "handler did not return a DataFrame"
            return out
        # Apply requested processor stack in order.
        for spec in req.processors:
            try:
                proc = build_from_config(spec)
                if hasattr(proc, "fit"):
                    try:
                        proc.fit(df)
                    except Exception:  # noqa: BLE001
                        pass
                df = proc(df)
            except Exception as exc:  # noqa: BLE001
                logger.exception("preview processor %s failed", spec.get("class"))
                out["error"] = f"{spec.get('class', 'processor')}: {exc}"
                break
        sample = df.tail(req.rows).copy() if hasattr(df, "tail") else df
        try:
            sample = sample.reset_index().head(req.rows)
        except Exception:  # noqa: BLE001
            pass
        if hasattr(sample, "columns"):
            out["columns"] = [str(c) for c in sample.columns]
        for col in getattr(sample, "columns", []):
            try:
                sample[col] = sample[col].astype(str)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(sample, "to_dict"):
            out["rows"] = sample.to_dict(orient="records")
        out["n_rows"] = int(len(df))
        out["n_cols"] = int(getattr(df, "shape", (0, 0))[1] if hasattr(df, "shape") else 0)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return out


# ---------------------------------------------------------------------------
# Recipe catalog — surfaces YAML files under configs/ml/ for the UI.
# ---------------------------------------------------------------------------


@router.get("/recipes")
def list_recipes() -> list[dict[str, Any]]:
    """Enumerate `configs/ml/**/*.yaml` recipes for the training UI."""
    import os
    from pathlib import Path

    import yaml

    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent.parent
    base = repo_root / "configs" / "ml"
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for path in sorted(base.rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            logger.debug("skip recipe %s: %s", path, exc)
            continue
        rel = path.relative_to(repo_root).as_posix()
        out.append(
            {
                "id": rel,
                "name": data.get("name") or path.stem,
                "description": data.get("description") or "",
                "group": path.parent.name,
                "path": rel,
                "model_class": ((data.get("model") or {}).get("class")),
                "dataset_class": ((data.get("dataset") or {}).get("class")),
            }
        )
    return out


@router.get("/frameworks")
def list_frameworks() -> dict[str, Any]:
    return {
        "frameworks": [
            {
                "id": "scikit-learn",
                "extra": "ml",
                "models": ["SklearnRegressorModel", "SklearnClassifierModel", "SklearnPipelineModel"],
            },
            {
                "id": "forecasting",
                "extra": "ml-forecast",
                "models": ["ProphetForecastModel", "SktimeForecastModel", "SktimeReductionForecastModel"],
            },
            {"id": "pyod", "extra": "ml-anomaly", "models": ["PyODAnomalyModel"]},
            {"id": "keras", "extra": "ml-keras/ml-tensorflow", "models": ["KerasMLPModel", "KerasLSTMModel"]},
            {"id": "transformers", "extra": "ml-transformers", "models": ["HuggingFaceTextSignalModel"]},
            {"id": "gbdt", "extra": "ml", "models": ["LGBModel", "XGBModel", "CatBoostModel", "DEnsembleModel"]},
            {"id": "pytorch", "extra": "ml-torch", "models": ["DNNModel", "LSTMModel", "GRUModel", "TransformerModel", "TCNModel"]},
        ]
    }


@router.get("/flows")
def list_ml_flows() -> list[dict[str, Any]]:
    """Enumerate every workbench flow registered in :mod:`aqp.ml.flows`.

    Used by the webui experiment-builder palette and the interactive
    workbench drawer to render parameter forms dynamically.
    """
    from aqp.ml.flows import list_flows

    return list_flows()


@router.post("/flows/{flow}/preview")
def preview_flow(flow: str, req: FlowPreviewRequest) -> dict[str, Any]:
    from aqp.ml.flows import run_flow

    payload = req.model_dump()
    return run_flow(flow, payload)


@router.post("/flows/{flow}/preview-task", response_model=TaskAccepted)
def preview_flow_task(flow: str, req: FlowPreviewRequest) -> TaskAccepted:
    from aqp.tasks.ml_tasks import preview_ml_flow

    async_result = preview_ml_flow.delay(flow, req.model_dump())
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/evaluations/{task_id}")
def get_evaluation(task_id: str) -> dict[str, Any]:
    """Fetch persisted results from an `evaluate_ml_model` Celery task.

    Looks up MLflow runs tagged with the task id; falls back to the
    latest evaluation row attached to the most recent ``ModelVersion``
    when MLflow is unavailable.
    """
    try:
        import mlflow

        from aqp.config import settings

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        client = mlflow.tracking.MlflowClient()
        runs = client.search_runs(
            experiment_ids=[
                exp.experiment_id
                for exp in client.search_experiments()
            ],
            filter_string=f"tags.task_id = '{task_id}'",
            max_results=1,
        )
        if runs:
            run = runs[0]
            return {
                "task_id": task_id,
                "mlflow_run_id": run.info.run_id,
                "metrics": dict(run.data.metrics or {}),
                "params": dict(run.data.params or {}),
                "tags": dict(run.data.tags or {}),
                "status": run.info.status,
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("MLflow lookup for %s failed: %s", task_id, exc)

    # Fallback — return whatever metrics live on the most recent model.
    with get_session() as session:
        row = session.execute(
            select(ModelVersion).order_by(desc(ModelVersion.created_at)).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "no evaluations available")
        return {
            "task_id": task_id,
            "mlflow_run_id": (row.metrics or {}).get("mlflow_run_id"),
            "metrics": dict(row.metrics or {}),
            "tags": {},
            "status": "completed",
            "registry_name": row.registry_name,
        }


# ---------------------------------------------------------------------------
# Live test bridge — runs deployed model inference on a /live subscription.
# ---------------------------------------------------------------------------


class LiveTestStartRequest(BaseModel):
    deployment_id: str = Field(..., description="ModelDeployment.id")
    venue: str = Field(default="simulated", description="alpaca | ibkr | kafka | simulated")
    symbols: list[str] = Field(default_factory=list)
    poll_cadence_seconds: float = Field(default=5.0, ge=1.0, le=60.0)


# ---------------------------------------------------------------------------
# Interactive ML test workbench (ML expansion)
# ---------------------------------------------------------------------------


@router.post("/test/single")
def test_single_predict(req: TestSinglePredictRequest) -> dict[str, Any]:
    """Score a single feature row through a deployed model.

    When ``sync=true`` (default) the prediction runs in-process for
    sub-second response. Setting ``sync=false`` queues the work on the
    ``ml`` Celery queue and returns a ``TaskAccepted`` payload.
    """
    if not req.sync:
        from aqp.tasks.ml_test_tasks import predict_single

        async_result = predict_single.delay(
            deployment_id=req.deployment_id,
            feature_row=req.feature_row,
            vt_symbol=req.vt_symbol,
        )
        return {
            "task_id": async_result.id,
            "stream_url": f"/chat/stream/{async_result.id}",
        }
    # Synchronous path — re-use the same worker function for parity.
    from aqp.tasks.ml_test_tasks import predict_single as _task

    fn = _task.run if hasattr(_task, "run") else _task
    return fn(
        deployment_id=req.deployment_id,
        feature_row=req.feature_row,
        vt_symbol=req.vt_symbol,
    )


@router.post("/test/batch", response_model=TaskAccepted)
def test_batch_predict(req: TestBatchPredictRequest) -> TaskAccepted:
    from aqp.tasks.ml_test_tasks import predict_batch

    async_result = predict_batch.delay(
        deployment_id=req.deployment_id,
        symbols=req.symbols,
        start=req.start,
        end=req.end,
        last_n=req.last_n,
        iceberg_identifier=req.iceberg_identifier,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.post("/test/compare", response_model=TaskAccepted)
def test_compare(req: TestCompareRequest) -> TaskAccepted:
    if req.deployment_id_a == req.deployment_id_b:
        raise HTTPException(400, "deployment_id_a and deployment_id_b must differ")
    from aqp.tasks.ml_test_tasks import compare_models

    async_result = compare_models.delay(
        deployment_id_a=req.deployment_id_a,
        deployment_id_b=req.deployment_id_b,
        symbols=req.symbols,
        start=req.start,
        end=req.end,
        last_n=req.last_n,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.post("/test/scenario")
def test_scenario(req: TestScenarioRequest) -> dict[str, Any]:
    """Sensitivity perturbation table for a single feature row.

    Synchronous by default (perturbing a single row across N values is
    cheap). Pass ``sync=false`` to fan-out via Celery for very large
    perturbation lists.
    """
    if not req.sync:
        from aqp.tasks.ml_test_tasks import scenario_perturbation

        async_result = scenario_perturbation.delay(
            deployment_id=req.deployment_id,
            feature_row=req.feature_row,
            perturbations=req.perturbations,
        )
        return {
            "task_id": async_result.id,
            "stream_url": f"/chat/stream/{async_result.id}",
        }
    from aqp.tasks.ml_test_tasks import scenario_perturbation as _task

    fn = _task.run if hasattr(_task, "run") else _task
    return fn(
        deployment_id=req.deployment_id,
        feature_row=req.feature_row,
        perturbations=req.perturbations,
    )


@router.post("/test/upload-csv")
async def test_upload_csv(deployment_id: str, file: Any = None) -> dict[str, Any]:
    """Upload a CSV and run inference row-by-row.

    Size-capped via ``settings.ml_workbench_max_csv_mb``. The CSV must
    have one feature column per model input; rows are scored
    synchronously and the result includes per-row predictions and a
    summary distribution.
    """
    from fastapi import File, UploadFile

    # FastAPI doesn't auto-bind File() in unsigned annotations; re-declare.
    if file is None or not hasattr(file, "read"):
        raise HTTPException(400, "file is required (multipart/form-data)")
    upload: UploadFile = file  # type: ignore[assignment]
    max_mb = int(getattr(settings, "ml_workbench_max_csv_mb", 20))
    payload = await upload.read()
    if len(payload) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"CSV exceeds {max_mb} MB cap")

    import io

    try:
        df = pd.read_csv(io.BytesIO(payload))
    except Exception as exc:
        raise HTTPException(400, f"could not parse CSV: {exc}") from exc

    from aqp.tasks.ml_test_tasks import _load_alpha

    alpha = _load_alpha(deployment_id)
    if alpha._model is None:  # noqa: SLF001
        raise HTTPException(400, "deployment did not resolve to a usable model")
    try:
        preds = alpha._predict(df.to_numpy(dtype=float))  # noqa: SLF001
    except Exception:
        preds = alpha._model.predict(df)
    arr = np.asarray(preds, dtype=float).reshape(-1)
    out = df.copy()
    out["__prediction__"] = arr[: len(out)]
    return {
        "deployment_id": deployment_id,
        "n_rows": int(len(df)),
        "predictions_summary": {
            "mean": float(arr.mean()) if arr.size else 0.0,
            "std": float(arr.std()) if arr.size else 0.0,
            "min": float(arr.min()) if arr.size else 0.0,
            "max": float(arr.max()) if arr.size else 0.0,
        },
        "rows": out.head(500).to_dict(orient="records"),
    }


@router.post("/live-test/start")
async def live_test_start(req: LiveTestStartRequest) -> dict[str, Any]:
    """Start a live model-inference bridge.

    Forwards to ``POST /live/subscribe`` for the live data stream and
    returns the channel id so the UI can attach a WebSocket. The
    bridge runs predictions in-process via the deployed model artifact;
    when the deployment artifact isn't loadable we still return a valid
    channel that emits raw bars so the UI overlays gracefully.
    """
    if not req.symbols:
        raise HTTPException(400, "symbols must not be empty")

    with get_session() as session:
        dep = session.get(ModelDeployment, req.deployment_id)
        if dep is None:
            raise HTTPException(404, "deployment not found")

    base = settings.api_url.rstrip("/")
    payload = {
        "venue": req.venue,
        "symbols": req.symbols,
        "poll_cadence_seconds": req.poll_cadence_seconds,
    }
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{base}/live/subscribe", json=payload)
            resp.raise_for_status()
            sub = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"live/subscribe failed: {exc}") from exc

    return {
        "channel_id": sub.get("channel_id"),
        "ws_url": sub.get("ws_url"),
        "deployment_id": req.deployment_id,
        "symbols": req.symbols,
    }


@router.delete("/live-test/{channel_id}")
async def live_test_stop(channel_id: str) -> dict[str, Any]:
    base = settings.api_url.rstrip("/")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{base}/live/subscribe/{channel_id}")
            resp.raise_for_status()
        return {"channel_id": channel_id, "stopped": True}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"live/subscribe stop failed: {exc}") from exc


@router.get("/recipes/{recipe_id:path}")
def get_recipe(recipe_id: str) -> dict[str, Any]:
    """Return the parsed YAML body for a single recipe by relative path."""
    from pathlib import Path

    import yaml

    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent.parent
    safe = recipe_id.replace("\\", "/")
    if ".." in safe.split("/"):
        raise HTTPException(400, "invalid recipe id")
    path = (repo_root / safe).resolve()
    try:
        path.relative_to(repo_root)
    except ValueError:
        raise HTTPException(400, "invalid recipe id") from None
    if not path.exists() or path.suffix.lower() not in {".yaml", ".yml"}:
        raise HTTPException(404, f"no recipe at {recipe_id}")
    try:
        body = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"could not parse {recipe_id}: {exc}") from exc
    return {
        "id": recipe_id,
        "path": recipe_id,
        "body": body,
        "dataset_cfg": body.get("dataset") or body.get("dataset_cfg") or {},
        "model_cfg": body.get("model") or body.get("model_cfg") or {},
        "records": body.get("records") or [],
    }
