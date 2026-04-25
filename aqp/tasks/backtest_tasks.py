"""Celery tasks for backtesting + WFO + Monte Carlo."""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.backtest_tasks.run_backtest")
def run_backtest(self, cfg: dict[str, Any], run_name: str = "adhoc") -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Loading config and data…")
    try:
        from aqp.backtest.runner import run_backtest_from_config

        emit(task_id, "running", "Event-driven replay…")
        result = run_backtest_from_config(cfg, run_name=run_name)
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("backtest task failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.backtest_tasks.run_walk_forward")
def run_walk_forward(self, cfg: dict[str, Any], train: int = 252, test: int = 63, step: int = 63) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Starting walk-forward optimisation…")
    try:
        from aqp.backtest.walk_forward import run_walk_forward as _run

        result = _run(cfg, train_window_days=train, test_window_days=test, step_days=step)
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("WFO task failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.backtest_tasks.run_monte_carlo")
def run_monte_carlo(self, backtest_id: str, n_runs: int = 500, method: str = "bootstrap") -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Running Monte Carlo ({n_runs} paths)…")
    try:
        from aqp.backtest.metrics import _fetch_equity_curve
        from aqp.backtest.monte_carlo import run_monte_carlo as _mc

        eq = _fetch_equity_curve(backtest_id)
        result = _mc(eq, n_runs=n_runs, method=method)
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("MC task failed")
        emit_error(task_id, str(e))
        raise
