"""Celery + paper-session signal hooks that auto-open MLflow runs.

Importing this module is enough to register the hooks. The Celery app
imports it on startup so every backtest / paper / factor task opens an
MLflow run whose tags include the task id. A separate hook is exposed
for paper sessions to call from :class:`aqp.trading.session.PaperTradingSession`.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings
from aqp.mlops import mlflow_client

logger = logging.getLogger(__name__)

_registered_celery = False

# Tasks that manage their OWN MLflow runs (backtest runner, ML training,
# factor eval, paper sessions, walk-forward, RL training). The task_prerun
# hook skips these to avoid double-opened parent runs that swallow the
# nested runs created by ``log_backtest`` / ``log_alpha_training`` / etc.
_AUTOLOG_SKIP_TASKS: set[str] = {
    "aqp.tasks.backtest_tasks.run_backtest",
    "aqp.tasks.backtest_tasks.run_walk_forward",
    "aqp.tasks.backtest_tasks.run_monte_carlo",
    "aqp.tasks.factor_tasks.evaluate_factor",
    "aqp.tasks.paper_tasks.run_paper",
    "aqp.tasks.training_tasks.train_rl",
    "aqp.tasks.training_tasks.evaluate_rl",
    "aqp.tasks.ml_tasks.train_ml_model",
    "aqp.tasks.ml_tasks.evaluate_ml_model",
}


def register_celery_signals() -> None:
    """Wire Celery ``task_prerun`` / ``task_postrun`` to MLflow.

    Idempotent. Tasks in :data:`_AUTOLOG_SKIP_TASKS` manage their own runs
    and are deliberately skipped so we don't end up with two parents per
    task (one from the hook, one from ``log_backtest`` / etc.). Called once
    from :mod:`aqp.tasks.celery_app` after the worker process has been
    initialised.
    """
    global _registered_celery
    if _registered_celery:
        return
    try:
        from celery.signals import task_postrun, task_prerun
    except Exception:
        logger.debug("celery not available — skipping autolog wiring")
        return
    if not settings.mlflow_tracking_uri:
        return

    @task_prerun.connect
    def _prerun(task_id=None, task=None, args=None, kwargs=None, **extra):
        try:
            if getattr(task, "name", None) in _AUTOLOG_SKIP_TASKS:
                return
            import mlflow

            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            mlflow_client.ensure_experiment()
            run = mlflow.start_run(
                run_name=f"{task.name}-{(task_id or '')[:8]}",
                nested=False,
                tags={
                    "aqp.celery.task": task.name,
                    "aqp.celery.task_id": str(task_id) if task_id else "",
                },
            )
            task.mlflow_run_id = run.info.run_id  # type: ignore[attr-defined]
        except Exception:
            logger.debug("task_prerun MLflow hook failed", exc_info=True)

    @task_postrun.connect
    def _postrun(task_id=None, task=None, retval=None, state=None, **extra):
        try:
            if getattr(task, "name", None) in _AUTOLOG_SKIP_TASKS:
                return
            import mlflow

            mlflow.set_tag("aqp.celery.state", str(state))
            mlflow.end_run(status="FINISHED" if state == "SUCCESS" else "FAILED")
        except Exception:
            logger.debug("task_postrun MLflow hook failed", exc_info=True)

    _registered_celery = True


# ---------------------------------------------------------------------------
# Paper-session hook
# ---------------------------------------------------------------------------


def paper_session_end_hook(result: dict[str, Any], config: dict[str, Any]) -> None:
    """Fire at the end of a paper session to persist its MLflow run."""
    try:
        mlflow_client.log_paper_session(result=result, config=config)
    except Exception:
        logger.exception("paper_session_end_hook failed")


def factor_report_hook(report: Any) -> None:
    """Fire after a :class:`FactorReport` is produced to persist it."""
    try:
        mlflow_client.log_factor_run(
            factor_name=getattr(report, "factor_name", "factor"),
            ic_stats=getattr(report, "ic_stats", {}),
            cumulative_returns=getattr(report, "cumulative_returns", None),
            turnover_mean=float(getattr(report, "turnover", []).mean())
            if hasattr(report, "turnover") and len(getattr(report, "turnover", [])) > 0
            else None,
        )
    except Exception:
        logger.exception("factor_report_hook failed")
