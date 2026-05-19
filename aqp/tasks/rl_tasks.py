"""Celery tasks for the metaclass-driven RL stack.

Every task wraps :class:`aqp.rl.runtime.RLRuntime` so spec-version
snapshotting, ``rl_runs`` row creation, Iceberg trajectory persistence
and progress emits happen automatically.

The legacy :mod:`aqp.tasks.training_tasks` module is kept for
backwards-compat (the old ``/rl/train`` route still resolves there);
new callers should target these tasks instead.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app
from aqp.tasks.secure_task import SecureTask

logger = logging.getLogger(__name__)


def _build_runtime(spec_payload: dict[str, Any], task_id: str | None) -> Any:
    from aqp.rl.runtime import RLRuntime
    from aqp.rl.spec import RLExperimentSpec

    spec = RLExperimentSpec.model_validate(spec_payload)
    return RLRuntime(spec, task_id=task_id)


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.rl_tasks.train_rl_experiment")
def train_rl_experiment(
    self,
    spec_payload: dict[str, Any],
    *,
    run_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Bootstrapping RL experiment runtime…")
    try:
        runtime = _build_runtime(spec_payload, task_id)
        result = runtime.train(run_name=run_name, overrides=overrides or {})
        return result.to_dict()
    except Exception as exc:  # pragma: no cover
        logger.exception("train_rl_experiment failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.rl_tasks.evaluate_rl_experiment")
def evaluate_rl_experiment(
    self,
    spec_payload: dict[str, Any],
    *,
    checkpoint: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Evaluating checkpoint {checkpoint}…")
    try:
        runtime = _build_runtime(spec_payload, task_id)
        result = runtime.evaluate(checkpoint=checkpoint, overrides=overrides or {})
        return result.to_dict()
    except Exception as exc:  # pragma: no cover
        logger.exception("evaluate_rl_experiment failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.rl_tasks.replay_trajectories")
def replay_trajectories(
    self,
    spec_payload: dict[str, Any],
    *,
    checkpoint: str,
    new_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Replaying trained policy on new window…")
    try:
        runtime = _build_runtime(spec_payload, task_id)
        result = runtime.replay(checkpoint=checkpoint, new_window=new_window or {})
        return result.to_dict()
    except Exception as exc:  # pragma: no cover
        logger.exception("replay_trajectories failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.rl_tasks.walk_forward_ensemble")
def walk_forward_ensemble(
    self,
    spec_payload: dict[str, Any],
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Running walk-forward ensemble…")
    try:
        runtime = _build_runtime(spec_payload, task_id)
        result = runtime.walk_forward(overrides=overrides or {})
        return result.to_dict()
    except Exception as exc:  # pragma: no cover
        logger.exception("walk_forward_ensemble failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.rl_tasks.best_of_n_search")
def best_of_n_search(
    self,
    spec_payload: dict[str, Any],
    *,
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Best-of-{len(members)} search…")
    try:
        spec_payload = dict(spec_payload)
        spec_payload["ensembler"] = {
            "spec": {
                "class": "BestOfNRunner",
                "module_path": "aqp.rl.ensemblers.best_of_n",
                "kwargs": {"members": members},
            }
        }
        runtime = _build_runtime(spec_payload, task_id)
        result = runtime.walk_forward()
        return result.to_dict()
    except Exception as exc:  # pragma: no cover
        logger.exception("best_of_n_search failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.rl_tasks.paper_trade_rl")
def paper_trade_rl(
    self,
    spec_payload: dict[str, Any],
    *,
    checkpoint: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Starting RL paper-trading session…")
    try:
        runtime = _build_runtime(spec_payload, task_id)
        result = runtime.paper(checkpoint=checkpoint, overrides=overrides or {})
        return result.to_dict()
    except Exception as exc:  # pragma: no cover
        logger.exception("paper_trade_rl failed")
        emit_error(task_id, str(exc))
        raise


__all__ = [
    "best_of_n_search",
    "evaluate_rl_experiment",
    "paper_trade_rl",
    "replay_trajectories",
    "train_rl_experiment",
    "walk_forward_ensemble",
]
