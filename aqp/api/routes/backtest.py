"""Backtest endpoints — submit / inspect / visualise + parameter sweeps."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import (
    BacktestRequest,
    BacktestSummary,
    MonteCarloRequest,
    TaskAccepted,
    WalkForwardRequest,
)
from aqp.backtest.metrics import plot_drawdown, plot_equity_curve
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    BacktestInterrupt,
    BacktestRun,
    OptimizationRun,
    OptimizationTrial,
)
from aqp.tasks.backtest_tasks import run_backtest, run_monte_carlo, run_walk_forward

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run", response_model=TaskAccepted)
def submit_backtest(req: BacktestRequest) -> TaskAccepted:
    async_result = run_backtest.delay(req.config, req.run_name)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/walk_forward", response_model=TaskAccepted)
def submit_wfo(req: WalkForwardRequest) -> TaskAccepted:
    async_result = run_walk_forward.delay(
        req.config, req.train_window_days, req.test_window_days, req.step_days
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/monte_carlo", response_model=TaskAccepted)
def submit_mc(req: MonteCarloRequest) -> TaskAccepted:
    async_result = run_monte_carlo.delay(req.backtest_id, req.n_runs, req.method)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/runs", response_model=list[BacktestSummary])
def list_runs(limit: int = 50) -> list[BacktestSummary]:
    with get_session() as s:
        rows = s.execute(
            select(BacktestRun).order_by(desc(BacktestRun.created_at)).limit(limit)
        ).scalars().all()
        return [
            BacktestSummary(
                id=r.id,
                status=r.status,
                start=r.start,
                end=r.end,
                sharpe=r.sharpe,
                sortino=r.sortino,
                max_drawdown=r.max_drawdown,
                total_return=r.total_return,
                final_equity=r.final_equity,
                dataset_hash=r.dataset_hash,
                model_deployment_id=(r.metrics or {}).get("model_deployment_id"),
                created_at=r.created_at,
            )
            for r in rows
        ]


@router.get("/runs/{backtest_id}", response_model=BacktestSummary)
def get_run(backtest_id: str) -> BacktestSummary:
    with get_session() as s:
        r = s.get(BacktestRun, backtest_id)
        if r is None:
            raise HTTPException(404, "no such run")
        return BacktestSummary(
            id=r.id,
            status=r.status,
            start=r.start,
            end=r.end,
            sharpe=r.sharpe,
            sortino=r.sortino,
            max_drawdown=r.max_drawdown,
            total_return=r.total_return,
            final_equity=r.final_equity,
            dataset_hash=r.dataset_hash,
            model_deployment_id=(r.metrics or {}).get("model_deployment_id"),
            created_at=r.created_at,
        )


@router.get("/runs/{backtest_id}/plot/{kind}")
def plot(backtest_id: str, kind: str) -> dict:
    if kind == "equity":
        fig = plot_equity_curve(backtest_id)
    elif kind == "drawdown":
        fig = plot_drawdown(backtest_id)
    else:
        raise HTTPException(400, f"unknown kind: {kind}")
    import json

    return json.loads(fig.to_json())


# ---------------------------------------------------------------------------
# Parameter-sweep optimiser
# ---------------------------------------------------------------------------


class ParameterSpec(BaseModel):
    """Single sweep parameter.

    Specify either an explicit ``values`` list or a ``low``/``high``/``step``
    numeric range. ``path`` uses dotted notation into the strategy config,
    e.g. ``"strategy.kwargs.alpha_model.kwargs.lookback"``.
    """

    path: str
    values: list[Any] | None = None
    low: float | None = None
    high: float | None = None
    step: float | None = None


class OptimizeRequest(BaseModel):
    config: dict[str, Any] = Field(..., description="Base strategy YAML config")
    parameters: list[ParameterSpec] = Field(..., description="Sweep parameters")
    method: str = Field(default="grid", description="grid | random")
    metric: str = Field(default="sharpe", description="objective to maximise")
    n_random: int = Field(default=32, ge=1, le=1024)
    strategy_id: str | None = None
    run_name: str = Field(default="sweep")
    max_trials: int = Field(default=200, ge=1, le=2048)


class OptimizationSummary(BaseModel):
    id: str
    status: str
    run_name: str
    method: str
    metric: str
    n_trials: int
    n_completed: int
    best_metric_value: float | None = None
    best_trial_id: str | None = None
    strategy_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class OptimizationTrialOut(BaseModel):
    id: str
    trial_index: int
    status: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    metric_value: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    total_return: float | None = None
    max_drawdown: float | None = None
    final_equity: float | None = None
    backtest_id: str | None = None


class OptimizationDetail(OptimizationSummary):
    summary: dict[str, Any] = Field(default_factory=dict)
    parameter_space: list[dict[str, Any]] = Field(default_factory=list)
    trials: list[OptimizationTrialOut] = Field(default_factory=list)


@router.post("/optimize", response_model=TaskAccepted)
def submit_optimization(req: OptimizeRequest) -> TaskAccepted:
    """Expand the parameter space, persist the run + trials, and queue work.

    The expansion happens on the API side so the UI can watch trials
    complete one-by-one; the worker task then pops queued trials until
    the run is exhausted.
    """
    from aqp.backtest.optimizer import ParameterSpec as SweepSpec
    from aqp.backtest.optimizer import generate_trials
    from aqp.tasks.optimize_tasks import run_optimization

    specs = [
        SweepSpec(
            path=p.path,
            values=p.values,
            low=p.low,
            high=p.high,
            step=p.step,
        )
        for p in req.parameters
    ]
    trials = list(
        generate_trials(
            req.config,
            specs,
            method=req.method,
            n_random=req.n_random,
        )
    )
    if not trials:
        raise HTTPException(400, "parameter space expanded to zero trials")
    if len(trials) > req.max_trials:
        raise HTTPException(
            400,
            f"{len(trials)} trials exceeds max_trials={req.max_trials}; use random search or raise the cap.",
        )

    with get_session() as s:
        parent = OptimizationRun(
            run_name=req.run_name,
            method=req.method,
            metric=req.metric,
            strategy_id=req.strategy_id,
            n_trials=len(trials),
            parameter_space=[p.model_dump() for p in req.parameters],
            base_config=req.config,
            status="queued",
        )
        s.add(parent)
        s.flush()
        run_id = parent.id
        for idx, (params, _cfg) in enumerate(trials):
            s.add(
                OptimizationTrial(
                    run_id=run_id,
                    trial_index=idx,
                    parameters=params,
                    status="queued",
                )
            )

    async_result = run_optimization.delay(run_id)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/optimize", response_model=list[OptimizationSummary])
def list_optimizations(limit: int = 50) -> list[OptimizationSummary]:
    with get_session() as s:
        rows = s.execute(
            select(OptimizationRun)
            .order_by(desc(OptimizationRun.created_at))
            .limit(limit)
        ).scalars().all()
        return [_opt_summary(r) for r in rows]


@router.get("/optimize/{run_id}", response_model=OptimizationDetail)
def get_optimization(run_id: str) -> OptimizationDetail:
    with get_session() as s:
        run = s.get(OptimizationRun, run_id)
        if run is None:
            raise HTTPException(404, "no such optimization run")
        trials = s.execute(
            select(OptimizationTrial)
            .where(OptimizationTrial.run_id == run_id)
            .order_by(OptimizationTrial.trial_index)
        ).scalars().all()
        summary = _opt_summary(run).model_dump()
        return OptimizationDetail(
            **summary,
            summary=run.summary or {},
            parameter_space=list(run.parameter_space or []),
            trials=[_trial_out(t) for t in trials],
        )


@router.get("/optimize/{run_id}/results")
def optimization_results(run_id: str) -> dict[str, Any]:
    """Compact trials payload for the heatmap / top-N panel."""
    with get_session() as s:
        run = s.get(OptimizationRun, run_id)
        if run is None:
            raise HTTPException(404, "no such optimization run")
        trials = s.execute(
            select(OptimizationTrial)
            .where(OptimizationTrial.run_id == run_id)
            .order_by(OptimizationTrial.trial_index)
        ).scalars().all()
        return {
            "run_id": run_id,
            "metric": run.metric,
            "status": run.status,
            "summary": run.summary or {},
            "parameter_space": list(run.parameter_space or []),
            "trials": [
                {
                    "trial_index": t.trial_index,
                    "status": t.status,
                    "parameters": t.parameters or {},
                    "metric_value": t.metric_value,
                    "sharpe": t.sharpe,
                    "sortino": t.sortino,
                    "total_return": t.total_return,
                    "max_drawdown": t.max_drawdown,
                    "final_equity": t.final_equity,
                    "backtest_id": t.backtest_id,
                }
                for t in trials
            ],
        }


def _opt_summary(row: OptimizationRun) -> OptimizationSummary:
    return OptimizationSummary(
        id=row.id,
        status=row.status,
        run_name=row.run_name,
        method=row.method,
        metric=row.metric,
        n_trials=row.n_trials,
        n_completed=row.n_completed,
        best_metric_value=row.best_metric_value,
        best_trial_id=row.best_trial_id,
        strategy_id=row.strategy_id,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _trial_out(t: OptimizationTrial) -> OptimizationTrialOut:
    return OptimizationTrialOut(
        id=t.id,
        trial_index=t.trial_index,
        status=t.status,
        parameters=t.parameters or {},
        metric_value=t.metric_value,
        sharpe=t.sharpe,
        sortino=t.sortino,
        total_return=t.total_return,
        max_drawdown=t.max_drawdown,
        final_equity=t.final_equity,
        backtest_id=t.backtest_id,
    )


# ---------------------------------------------------------------------------
# HITL phase 2: live mid-backtest interrupt endpoints (scaffolded).
# ---------------------------------------------------------------------------


class InterruptSummary(BaseModel):
    id: str
    backtest_id: str
    task_id: str | None = None
    ts: datetime | None = None
    rule: str | None = None
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    resolved_at: datetime | None = None


class InterruptResponseBody(BaseModel):
    action: str = Field(default="continue", description="continue | skip | replace")
    replacement_orders: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None


@router.get("/interrupts", response_model=list[InterruptSummary])
def list_interrupts(
    backtest_id: str | None = None,
    status: str = "pending",
    limit: int = 50,
) -> list[InterruptSummary]:
    """Return interrupts (default: pending) optionally filtered by backtest."""
    with get_session() as s:
        stmt = (
            select(BacktestInterrupt)
            .order_by(desc(BacktestInterrupt.created_at))
            .limit(limit)
        )
        if backtest_id:
            stmt = stmt.where(BacktestInterrupt.backtest_id == backtest_id)
        if status:
            stmt = stmt.where(BacktestInterrupt.status == status)
        rows = s.execute(stmt).scalars().all()
    return [_interrupt_summary(r) for r in rows]


@router.get("/interrupts/{interrupt_id}", response_model=InterruptSummary)
def get_interrupt(interrupt_id: str) -> InterruptSummary:
    with get_session() as s:
        row = s.get(BacktestInterrupt, interrupt_id)
        if row is None:
            raise HTTPException(404, f"no interrupt {interrupt_id}")
        return _interrupt_summary(row)


@router.post("/interrupts/{interrupt_id}/respond")
def respond_interrupt(
    interrupt_id: str, body: InterruptResponseBody
) -> dict[str, Any]:
    """Wake the engine waiting on this interrupt with the supplied resolution.

    Pushes the response onto the Redis list the engine BLPOPs against
    (``aqp:interrupt:<id>:response``) and updates the persisted row so
    other UI clients see the resolution immediately.
    """
    import json

    import redis

    from aqp.config import settings

    with get_session() as s:
        row = s.get(BacktestInterrupt, interrupt_id)
        if row is None:
            raise HTTPException(404, f"no interrupt {interrupt_id}")
        if row.status not in {"pending", "expired"}:
            raise HTTPException(
                409,
                f"interrupt {interrupt_id} is already {row.status}; cannot respond",
            )
        response_payload = body.model_dump()
        try:
            client = redis.Redis.from_url(
                settings.redis_pubsub_url, decode_responses=True
            )
            client.rpush(
                f"aqp:interrupt:{interrupt_id}:response",
                json.dumps(response_payload, default=str),
            )
            client.expire(f"aqp:interrupt:{interrupt_id}:response", 3600)
        except Exception as exc:
            raise HTTPException(500, f"could not push interrupt response: {exc}") from exc
        # Optimistically mark resolved; the worker will overwrite if it
        # needs to record a different terminal state.
        row.status = "resolved"
        row.response = response_payload
        row.resolved_at = datetime.utcnow()
    return {"interrupt_id": interrupt_id, "status": "resolved"}


def _interrupt_summary(row: BacktestInterrupt) -> InterruptSummary:
    return InterruptSummary(
        id=row.id,
        backtest_id=row.backtest_id,
        task_id=row.task_id,
        ts=row.ts,
        rule=row.rule,
        status=row.status,
        payload=row.payload or {},
        response=row.response or {},
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )
