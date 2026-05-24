"""Celery tasks for RL training and evaluation."""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.training_tasks.train_rl")
def train_rl(self, cfg: dict[str, Any], run_name: str | None = None) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Bootstrapping training environment…")
    try:
        from aqp.rl.trainer import train_from_config

        emit(task_id, "training", "Running trainer with mlflow autolog…")
        result = train_from_config(cfg, run_name=run_name)
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("train_rl failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.training_tasks.evaluate_rl")
def evaluate_rl(self, cfg: dict[str, Any], checkpoint: str) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Evaluating checkpoint {checkpoint}…")
    try:
        from aqp.rl.evaluator import evaluate_policy

        result = evaluate_policy(cfg, checkpoint)
        emit_done(task_id, result)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("evaluate_rl failed")
        emit_error(task_id, str(e))
        raise


_RL_APPLICATION_ENTRIES = {
    "stock_trading": ("aqp.rl.applications.stock_trading", "train_stock_trading"),
    "portfolio_allocation": (
        "aqp.rl.applications.portfolio_allocation",
        "train_portfolio_allocation",
    ),
    "cryptocurrency_trading": (
        "aqp.rl.applications.cryptocurrency_trading",
        "train_crypto_trading",
    ),
    "ensemble_strategy": (
        "aqp.rl.applications.ensemble_strategy",
        "train_ensemble",
    ),
    "imitation_learning": (
        "aqp.rl.applications.imitation_learning",
        "train_imitation",
    ),
    "fundamental_portfolio_drl": (
        "aqp.rl.applications.fundamental_portfolio_drl",
        "train_fundamental_portfolio_drl",
    ),
}


@celery_app.task(bind=True, name="aqp.tasks.training_tasks.run_rl_application")
def run_rl_application(
    self,
    name: str,
    params: dict[str, Any] | None = None,
    run_name: str | None = None,
) -> dict[str, Any]:
    """Dispatch a one-shot RL application from the ``/rl/applications`` registry."""
    import importlib

    task_id = self.request.id or "local"
    emit(task_id, "start", f"Starting RL application {name}")
    if name not in _RL_APPLICATION_ENTRIES:
        emit_error(task_id, f"unknown application {name!r}")
        raise ValueError(f"unknown application {name!r}")
    module_path, entry = _RL_APPLICATION_ENTRIES[name]
    try:
        mod = importlib.import_module(module_path)
        fn = getattr(mod, entry)
        kwargs = dict(params or {})
        if run_name is not None:
            kwargs.setdefault("run_name", run_name)
        emit(task_id, "running", f"Calling {module_path}.{entry}")
        result = fn(**kwargs)
        emit_done(task_id, result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("run_rl_application %s failed", name)
        emit_error(task_id, str(exc))
        raise
