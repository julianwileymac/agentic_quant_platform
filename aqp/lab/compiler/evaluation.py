"""Evaluation-mode compiler: GraphSpec → Celery group of N child runs.

Phase 3 ships the real grid + random + optuna sweep controllers (the
Ray Tune backend lands when the soft dep is installed). Every trial
runs through the same Testing compiler under the hood — we just
materialise the parameter override list here.

The Deflated Sharpe Ratio guard fires AFTER the sweep finishes
because ``DSR(observed_sr | total_trials_searched)`` only makes sense
once ``total_trials_searched`` is known. The runtime persists the
count onto ``LabRun.total_trials_searched`` so DSR can be re-derived
deterministically.
"""
from __future__ import annotations

from typing import Any

from aqp.lab.compiler import CompileContext, CompileResult
from aqp.lab.evaluation.sweep import grid_sweep, random_sweep
from aqp.lab.schema import GraphSpec


def compile_evaluation(spec: GraphSpec, ctx: CompileContext) -> CompileResult:
    if spec.mode != "evaluation":
        raise ValueError(
            f"compile_evaluation requires mode='evaluation', got {spec.mode!r}"
        )
    eval_cfg = spec.mode_config.evaluation
    sweep = eval_cfg.sweep if eval_cfg else None
    if sweep is None:
        raise ValueError("evaluation mode requires SweepConfig on mode_config.evaluation")

    algo = (sweep.algo or "grid").lower()
    if algo == "grid":
        ctrl = grid_sweep(dict(sweep.values), budget=sweep.budget or None)
    elif algo == "random":
        # ``ranges`` is dict[str, tuple[float, float]] — Pydantic
        # rebuilds tuples as lists when dumped to JSON, so normalise.
        ranges = {k: (float(v[0]), float(v[1])) for k, v in dict(sweep.ranges).items()}
        ctrl = random_sweep(ranges, budget=sweep.budget or 16, seed=sweep.seed)
    elif algo in {"optuna_tpe", "ray_tune_asha"}:
        # The Optuna / Ray controllers need a live ``objective``
        # callable, which we don't have at compile-time. The runtime
        # wires that callable from the upstream node's metric; for
        # now we emit the grid expansion as a deterministic fallback
        # so the route still returns a sensible plan.
        ctrl = grid_sweep(dict(sweep.values), budget=sweep.budget or None)
    else:
        raise ValueError(f"evaluation: unknown sweep algo {algo!r}")

    payload: dict[str, Any] = {
        "run_id": ctx.run_id,
        "task_id": ctx.task_id,
        "session_id": ctx.session_id,
        "lab_id": ctx.lab_id,
        "algo": ctrl.algo,
        "primary_metric": sweep.primary_metric,
        "maximize": sweep.maximize,
        "cv": sweep.cv,
        "cv_kwargs": dict(sweep.cv_kwargs or {}),
        "trials": [
            {"trial_id": t.trial_id, "params": dict(t.params)} for t in ctrl.trials
        ],
        "total_trials": ctrl.total_planned,
    }
    return CompileResult(
        mode="evaluation",
        target="celery_group",
        payload=payload,
        breadcrumbs=[
            {
                "compiler": "evaluation",
                "algo": ctrl.algo,
                "n_trials": ctrl.total_planned,
                "cv": sweep.cv,
            }
        ],
    )


__all__ = ["compile_evaluation"]
