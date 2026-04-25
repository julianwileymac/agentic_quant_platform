"""Parameter-sweep optimizer over :func:`run_backtest_from_config`.

Mirrors Lean's ``OptimizationParameter`` + ``GridSearchOptimizationStrategy``
shape (see ``inspiration/Lean-master/Optimizer``) but at Python-dict
granularity: each :class:`ParameterSpec` is a dotted key into the strategy
config (e.g. ``"strategy.kwargs.alpha_model.kwargs.lookback"``) paired with
either an explicit ``values`` list or a ``(start, stop, step)`` range.

Two strategies are shipped:

- :func:`grid_search` — Cartesian product of every parameter.
- :func:`random_search` — uniform sample of ``n`` parameter combinations
  (useful when the grid would be too large).

Both return an iterable of ``(parameters, resolved_config)`` tuples ready
for execution by the Celery task.
"""
from __future__ import annotations

import copy
import itertools
import logging
import random
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ParameterSpec:
    """Description of one sweep parameter."""

    path: str
    values: list[Any] | None = None
    low: float | None = None
    high: float | None = None
    step: float | None = None
    log_scale: bool = False

    def enumerate(self) -> list[Any]:
        if self.values is not None:
            return list(self.values)
        if None in (self.low, self.high, self.step):
            raise ValueError(f"ParameterSpec({self.path}) needs either values or low/high/step")
        low = float(self.low)
        high = float(self.high)
        step = float(self.step)
        if step <= 0:
            raise ValueError(f"step must be > 0 for {self.path}")
        out: list[Any] = []
        cur = low
        while cur <= high + 1e-9:
            out.append(self._as_number(cur))
            cur = round(cur + step, 10)
        return out

    def _as_number(self, value: float) -> Any:
        if self.step and float(self.step).is_integer() and float(value).is_integer():
            return int(value)
        return float(value)


def _set_dotted(config: dict[str, Any], path: str, value: Any) -> None:
    cur: Any = config
    keys = path.split(".")
    for key in keys[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = value


def _get_dotted(config: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = config
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def generate_trials(
    base_config: dict[str, Any],
    spaces: Iterable[ParameterSpec],
    *,
    method: str = "grid",
    n_random: int = 32,
    seed: int | None = 42,
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield ``(parameters, resolved_config)`` for each trial.

    ``parameters`` is a flat ``{path: value}`` map for easy persistence and
    plotting; ``resolved_config`` is the deep-updated strategy config.
    """
    specs = list(spaces)
    if not specs:
        raise ValueError("at least one parameter spec is required")
    if method == "grid":
        yield from _grid(base_config, specs)
    elif method in {"random", "random-search"}:
        yield from _random(base_config, specs, n=n_random, seed=seed)
    else:
        raise ValueError(f"unknown method: {method!r} (want 'grid' or 'random')")


def _grid(
    base: dict[str, Any], specs: list[ParameterSpec]
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    pools = [spec.enumerate() for spec in specs]
    for combo in itertools.product(*pools):
        params = {spec.path: val for spec, val in zip(specs, combo, strict=True)}
        cfg = copy.deepcopy(base)
        for path, value in params.items():
            _set_dotted(cfg, path, value)
        yield params, cfg


def _random(
    base: dict[str, Any],
    specs: list[ParameterSpec],
    *,
    n: int,
    seed: int | None,
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    rng = random.Random(seed)
    pools = [spec.enumerate() for spec in specs]
    seen: set[tuple[Any, ...]] = set()
    emitted = 0
    cap = max(1, int(n))
    total_grid = 1
    for pool in pools:
        total_grid *= max(1, len(pool))
    max_unique = min(cap, total_grid)
    while emitted < max_unique:
        combo = tuple(rng.choice(pool) for pool in pools)
        if combo in seen:
            continue
        seen.add(combo)
        params = {spec.path: val for spec, val in zip(specs, combo, strict=True)}
        cfg = copy.deepcopy(base)
        for path, value in params.items():
            _set_dotted(cfg, path, value)
        emitted += 1
        yield params, cfg


def summarise(trials: list[dict[str, Any]], metric: str = "sharpe") -> dict[str, Any]:
    """Top / bottom trial + quick stats for storage on ``OptimizationRun.summary``."""
    if not trials:
        return {"n_trials": 0, "metric": metric}
    completed = [t for t in trials if t.get("status") == "completed" and t.get(metric) is not None]
    if not completed:
        return {"n_trials": len(trials), "metric": metric, "completed": 0}
    values = [float(t.get(metric, 0.0) or 0.0) for t in completed]
    best = max(completed, key=lambda t: t.get(metric) or float("-inf"))
    worst = min(completed, key=lambda t: t.get(metric) or float("inf"))
    return {
        "n_trials": len(trials),
        "completed": len(completed),
        "metric": metric,
        "best_trial_index": best.get("trial_index"),
        "best_metric_value": best.get(metric),
        "worst_trial_index": worst.get("trial_index"),
        "worst_metric_value": worst.get(metric),
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }
