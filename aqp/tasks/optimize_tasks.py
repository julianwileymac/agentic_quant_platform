"""Celery tasks for parameter-sweep optimisation.

Dispatches :class:`OptimizationTrial` rows sequentially per run. Each trial
calls :func:`aqp.backtest.runner.run_backtest_from_config` directly so the
MLflow + DB persistence the normal backtest path provides is reused without
re-implementation.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.optimize_tasks.run_optimization", queue="backtest")
def run_optimization(
    self,
    run_id: str,
) -> dict[str, Any]:
    """Execute every queued :class:`OptimizationTrial` for ``run_id`` in order.

    The API side creates the ``OptimizationRun`` and its pre-expanded
    trial rows; the worker only needs to iterate and call the shared
    backtest runner. This keeps the UI responsive (trials start completing
    almost immediately) and makes partial results visible.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Starting optimization run {run_id}…")
    try:
        from sqlalchemy import select

        from aqp.backtest.optimizer import summarise
        from aqp.backtest.runner import run_backtest_from_config
        from aqp.persistence.db import get_session
        from aqp.persistence.models import OptimizationRun, OptimizationTrial

        with get_session() as s:
            run = s.get(OptimizationRun, run_id)
            if run is None:
                emit_error(task_id, f"no such run: {run_id}")
                return {"error": f"no such run: {run_id}"}
            run.status = "running"
            run.task_id = task_id
            metric = run.metric or "sharpe"
            base_cfg = run.base_config or {}

        while True:
            with get_session() as s:
                trial = s.execute(
                    select(OptimizationTrial)
                    .where(OptimizationTrial.run_id == run_id)
                    .where(OptimizationTrial.status == "queued")
                    .order_by(OptimizationTrial.trial_index)
                    .limit(1)
                ).scalar_one_or_none()
                if trial is None:
                    break
                trial.status = "running"
                trial_id = trial.id
                trial_index = trial.trial_index
                params = dict(trial.parameters or {})

            emit(
                task_id,
                "running",
                f"Trial {trial_index} — {params}",
                trial_index=trial_index,
            )
            try:
                cfg = _apply_params(base_cfg, params)
                result = run_backtest_from_config(
                    cfg,
                    run_name=f"opt-{run_id[:8]}-{trial_index}",
                    mlflow_log=False,
                )
                metric_value = float(result.get(metric) or 0.0)
                with get_session() as s:
                    tr = s.get(OptimizationTrial, trial_id)
                    if tr is not None:
                        tr.status = "completed"
                        tr.backtest_id = result.get("run_id")
                        tr.metric_value = metric_value
                        tr.sharpe = result.get("sharpe")
                        tr.sortino = result.get("sortino")
                        tr.total_return = result.get("total_return")
                        tr.max_drawdown = result.get("max_drawdown")
                        tr.final_equity = result.get("final_equity")
                        tr.completed_at = datetime.utcnow()
                    parent = s.get(OptimizationRun, run_id)
                    if parent is not None:
                        parent.n_completed = (parent.n_completed or 0) + 1
                        best_value = parent.best_metric_value
                        if best_value is None or metric_value > best_value:
                            parent.best_metric_value = metric_value
                            parent.best_trial_id = trial_id
            except Exception as exc:  # noqa: BLE001
                logger.exception("trial %s failed", trial_index)
                with get_session() as s:
                    tr = s.get(OptimizationTrial, trial_id)
                    if tr is not None:
                        tr.status = "error"
                        tr.error = str(exc)
                        tr.completed_at = datetime.utcnow()

        with get_session() as s:
            run = s.get(OptimizationRun, run_id)
            trials = s.execute(
                select(OptimizationTrial).where(OptimizationTrial.run_id == run_id)
            ).scalars().all()
            rows = [
                {
                    "trial_index": t.trial_index,
                    "status": t.status,
                    "parameters": t.parameters or {},
                    "metric": metric,
                    metric: t.metric_value,
                    "sharpe": t.sharpe,
                    "sortino": t.sortino,
                    "total_return": t.total_return,
                    "max_drawdown": t.max_drawdown,
                }
                for t in trials
            ]
            summary = summarise(rows, metric=metric)
            if run is not None:
                run.status = "completed"
                run.summary = summary
                run.completed_at = datetime.utcnow()

        emit_done(task_id, {"run_id": run_id, "summary": summary})
        return {"run_id": run_id, "summary": summary}
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_optimization failed")
        emit_error(task_id, str(exc))
        raise


def _apply_params(base_cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    import copy

    cfg = copy.deepcopy(base_cfg or {})
    for path, value in params.items():
        cur: Any = cfg
        keys = path.split(".")
        for key in keys[:-1]:
            if key not in cur or not isinstance(cur[key], dict):
                cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = value
    return cfg
