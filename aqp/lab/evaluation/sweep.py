"""Pluggable sweep controllers for the Evaluation compiler.

Each controller takes a :class:`SweepConfig` (already validated by the
schema) and a callable ``objective(trial)`` that returns the primary
metric. The Optuna / Ray Tune backends are soft deps — when missing
we degrade to grid / random.

The compiler's job is to expand the sweep config into a list of
serialisable :class:`SweepTrial` records the Celery group can pick up
without re-importing the controllers in every worker.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)


@dataclass
class SweepTrial:
    """One trial in a parameter sweep."""

    trial_id: int
    params: dict[str, Any]
    primary_metric: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class SweepController:
    """Static description of how to enumerate trials."""

    algo: str
    trials: list[SweepTrial] = field(default_factory=list)
    total_planned: int = 0


def grid_sweep(values: dict[str, list[Any]], budget: int | None = None) -> SweepController:
    if not values:
        return SweepController(algo="grid", trials=[SweepTrial(trial_id=0, params={})], total_planned=1)
    keys = sorted(values.keys())
    grids = [values[k] for k in keys]
    combos = [dict(zip(keys, combo)) for combo in product(*grids)]
    if budget and budget > 0:
        combos = combos[: int(budget)]
    trials = [SweepTrial(trial_id=i, params=p) for i, p in enumerate(combos)]
    return SweepController(algo="grid", trials=trials, total_planned=len(trials))


def random_sweep(
    ranges: dict[str, tuple[float, float]],
    budget: int = 16,
    seed: int = 42,
) -> SweepController:
    rng = random.Random(seed)
    trials: list[SweepTrial] = []
    for i in range(int(budget)):
        sample = {k: rng.uniform(lo, hi) for k, (lo, hi) in ranges.items()}
        trials.append(SweepTrial(trial_id=i, params=sample))
    return SweepController(algo="random", trials=trials, total_planned=len(trials))


def optuna_tpe_sweep(
    ranges: dict[str, tuple[float, float]],
    objective: Callable[[dict[str, Any]], float],
    budget: int = 16,
    seed: int = 42,
    maximize: bool = True,
) -> SweepController:
    """Optuna TPE sweep — soft dep. Falls back to random when missing."""
    try:
        import optuna  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        logger.warning("optuna not installed; falling back to random sweep")
        return random_sweep(ranges, budget=budget, seed=seed)

    direction = "maximize" if maximize else "minimize"
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction=direction, sampler=sampler)

    def _objective(trial: Any) -> float:
        params = {
            k: trial.suggest_float(k, lo, hi) for k, (lo, hi) in ranges.items()
        }
        return float(objective(params))

    study.optimize(_objective, n_trials=int(budget))
    trials = [
        SweepTrial(
            trial_id=t.number,
            params=dict(t.params),
            primary_metric=float(t.value) if t.value is not None else None,
        )
        for t in study.trials
    ]
    return SweepController(algo="optuna_tpe", trials=trials, total_planned=len(trials))


def aggregate_trial_metric(
    trials: Iterable[SweepTrial],
    *,
    primary: bool = True,
) -> list[float]:
    """Collect the primary metric across completed trials.

    Used by :func:`aqp.lab.evaluation.deflated_sharpe.deflated_sharpe_ratio`
    via the runtime aggregation step. Trials without a metric are
    filtered out (they typically errored).
    """
    out: list[float] = []
    for t in trials:
        v = t.primary_metric if primary else None
        if v is not None:
            out.append(float(v))
    return out


__all__ = [
    "SweepController",
    "SweepTrial",
    "aggregate_trial_metric",
    "grid_sweep",
    "optuna_tpe_sweep",
    "random_sweep",
]
