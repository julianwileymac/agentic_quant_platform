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


class BacktestDataSource(BaseModel):
    id: str
    name: str
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class BacktestDataSourceUpsert(BaseModel):
    id: str | None = None
    name: str
    kind: str = Field(default="parquet_root", description="bars_default | parquet_root | iceberg_table")
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


@router.get("/data-sources", response_model=list[BacktestDataSource])
def list_data_sources() -> list[BacktestDataSource]:
    from aqp.runtime.control_plane import list_backtest_data_sources

    return [BacktestDataSource(**row) for row in list_backtest_data_sources()]


@router.post("/data-sources", response_model=BacktestDataSource)
def upsert_data_source(req: BacktestDataSourceUpsert) -> BacktestDataSource:
    from aqp.runtime.control_plane import upsert_backtest_data_source

    row = upsert_backtest_data_source(req.model_dump())
    return BacktestDataSource(**row)


@router.delete("/data-sources/{source_id}")
def delete_data_source(source_id: str) -> dict[str, Any]:
    from aqp.runtime.control_plane import delete_backtest_data_source

    return {"id": source_id, "deleted": bool(delete_backtest_data_source(source_id))}


class ParquetInspectRequest(BaseModel):
    parquet_root: str = Field(..., description="Absolute path on the API host.")
    max_files: int = Field(default=5000, ge=1, le=50_000)


@router.post("/data-sources/inspect")
def inspect_data_source(req: ParquetInspectRequest) -> dict[str, Any]:
    """Probe a local parquet root and return a structured inspection report.

    The webui Settings page calls this before persisting a ``parquet_root``
    data source so users can see partition keys, columns, and a sample.
    """
    from aqp.data.parquet_inspector import inspect_root

    return inspect_root(req.parquet_root, max_files=int(req.max_files)).to_dict()


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


@router.get("/runs/{backtest_id}/timeline")
def get_run_timeline(
    backtest_id: str,
    vt_symbol: str | None = None,
    interval: str = "1d",
    limit_bars: int = 5000,
) -> dict[str, Any]:
    """Return OHLCV bars + signals/trades/decisions for a backtest run.

    Powers the "Decisions" tab in the backtest detail UI: candlestick
    chart with overlaid markers showing where the strategy decided to
    buy/sell. ``vt_symbol`` is required when the run trades multiple
    symbols; if omitted we pick the first one we see in the persisted
    timeline / strategy config.
    """
    import datetime as _dt

    from aqp.core.types import DataNormalizationMode, Symbol
    from aqp.data.duckdb_engine import DuckDBHistoryProvider

    with get_session() as s:
        run = s.get(BacktestRun, backtest_id)
        if run is None:
            raise HTTPException(404, "no such run")
        metrics = run.metrics or {}
        timeline = metrics.get("timeline") or {}
        strategy_cfg = metrics.get("strategy_config") or {}
        run_start = run.start
        run_end = run.end

    trades = list(timeline.get("trades", []) or [])
    signals = list(timeline.get("signals", []) or [])
    orders = list(timeline.get("orders", []) or [])

    # Pick a symbol if caller didn't specify one.
    selected = vt_symbol
    if not selected:
        for collection in (trades, signals, orders):
            for row in collection:
                if isinstance(row, dict) and row.get("vt_symbol"):
                    selected = str(row["vt_symbol"])
                    break
            if selected:
                break
    if not selected:
        kwargs = strategy_cfg.get("kwargs", {}) if isinstance(strategy_cfg, dict) else {}
        uni = kwargs.get("universe_model", {}).get("kwargs", {}) if isinstance(kwargs, dict) else {}
        candidates = uni.get("symbols") or []
        if candidates:
            sym = candidates[0]
            selected = sym if "." in sym else f"{sym}.NASDAQ"

    bars: list[dict[str, Any]] = []
    symbols_seen: list[str] = []
    if selected:
        try:
            sym = Symbol.parse(selected) if "." in selected else Symbol(ticker=selected)
            provider = DuckDBHistoryProvider()
            start_dt = run_start or _dt.datetime(2000, 1, 1)
            end_dt = run_end or _dt.datetime.utcnow()
            df = provider.get_bars_normalized(
                [sym],
                start_dt,
                end_dt,
                interval=interval,
                normalization=DataNormalizationMode.ADJUSTED,
            )
            if df is not None and not df.empty:
                df = df.sort_values("timestamp").tail(limit_bars).copy()
                df["timestamp"] = df["timestamp"].astype(str)
                bars = df.to_dict(orient="records")
        except Exception:  # noqa: BLE001 - timeline endpoint is best-effort
            bars = []

    def _filter_to_symbol(rows: list[Any]) -> list[Any]:
        if not selected:
            return rows
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            sym = r.get("vt_symbol")
            symbols_seen.append(str(sym)) if sym else None
            if not sym or sym == selected:
                out.append(r)
        return out

    return {
        "backtest_id": backtest_id,
        "vt_symbol": selected,
        "interval": interval,
        "available_symbols": sorted(set(symbols_seen)) or ([selected] if selected else []),
        "bars": bars,
        "trades": _filter_to_symbol(trades),
        "signals": _filter_to_symbol(signals),
        "orders": _filter_to_symbol(orders),
    }


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
