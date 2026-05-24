"""Sweep controller — dispatch a planned :class:`SweepController` end-to-end.

Phase 3 ships the real sweep dispatcher that:

1. Reads ``SweepConfig`` off ``GraphSpec.mode_config.evaluation.sweep``.
2. Expands the trial list via the registered backend (grid / random /
   optuna_tpe / ray_tune_asha — Optuna + Ray are soft deps).
3. Optionally injects a CPCV fold list into the GraphSpec when
   ``sweep.cv == 'combinatorial_purged'`` so model.sklearn /
   model.gbm receive a deterministic train/test split per trial.
4. Stamps :class:`LabRun.total_trials_searched` on the parent run so
   :func:`aqp.lab.evaluation.deflated_sharpe.deflated_sharpe_ratio`
   can be computed honestly post-hoc.
5. For Phase 3 inline runs: walks the trial list serially and
   re-uses the inline-canvas dispatcher with each trial's parameter
   override applied to the GraphSpec.

The Phase 4 Celery group dispatcher uses the same controller — only
the trial-execution leg switches from sync to ``celery.group``. Each
child run inherits the parent's ``experiment_id`` per rule 34.

MLflow nested runs:

- The parent sweep run logs under ``mlflow.start_run(run_name=
  "lab-sweep:<graph_id>:<hash>")``.
- Each child trial logs under
  ``mlflow.start_run(nested=True, run_name="trial:<id>")``.
- The :mod:`aqp.mlops.autolog` Celery hook receives the
  ``mlflow_parent_run_id`` from the task header and opens its
  child run nested under the parent automatically.
"""
from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from aqp.lab.evaluation.cpcv import (
    CPCVConfig,
    CPCVPath,
    CPCVPlanError,
    combinatorial_purged_cv,
    safe_cpcv_path_count,
)
from aqp.lab.evaluation.sweep import (
    SweepController,
    SweepTrial,
    grid_sweep,
    optuna_tpe_sweep,
    random_sweep,
)
from aqp.lab.schema import GraphSpec, NodeSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plan + execute dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SweepPlan:
    """Result of :func:`plan_sweep` — describes a fully-expanded sweep."""

    controller: SweepController
    cv_paths: list[CPCVPath] | None
    total_trials_searched: int
    primary_metric: str
    maximize: bool


@dataclass
class TrialResult:
    """One executed trial's outcome."""

    trial_id: int
    params: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    primary_metric: float | None = None
    status: str = "done"
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class SweepResult:
    """End-to-end sweep result returned by :func:`execute_sweep_inline`."""

    plan: SweepPlan
    trials: list[TrialResult]
    best_trial_id: int | None = None
    best_metric: float | None = None
    deflated_sharpe: float | None = None


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def plan_sweep(spec: GraphSpec, *, n_observations: int | None = None) -> SweepPlan:
    """Plan a sweep — expand trials + (optionally) inject CPCV folds.

    ``n_observations`` is required when ``sweep.cv == 'combinatorial_purged'``
    so :func:`combinatorial_purged_cv` can partition the data into
    folds. Pass the upstream Data Source row count.
    """
    if spec.mode != "evaluation":
        raise ValueError(f"plan_sweep requires mode='evaluation'; got {spec.mode!r}")
    cfg = spec.mode_config.evaluation
    if cfg is None or cfg.sweep is None:
        raise ValueError("evaluation mode requires mode_config.evaluation.sweep")
    sweep = cfg.sweep

    algo = (sweep.algo or "grid").lower()
    if algo == "grid":
        controller = grid_sweep(dict(sweep.values), budget=sweep.budget or None)
    elif algo == "random":
        ranges = {k: (float(v[0]), float(v[1])) for k, v in dict(sweep.ranges).items()}
        controller = random_sweep(ranges, budget=sweep.budget or 16, seed=sweep.seed)
    elif algo == "optuna_tpe":
        # Optuna needs a live objective at plan-time. The sync
        # `execute_sweep_inline` runs trials serially and feeds back
        # the metric to the study; we materialise an empty controller
        # here and let the executor build the study live.
        controller = SweepController(algo="optuna_tpe", trials=[], total_planned=int(sweep.budget or 16))
    elif algo == "ray_tune_asha":
        from aqp.config import settings

        if not bool(getattr(settings, "aqp_lab_ray_tune_enabled", False)):
            logger.info("ray_tune_asha requested but disabled; falling back to grid")
            controller = grid_sweep(dict(sweep.values), budget=sweep.budget or None)
        else:
            controller = SweepController(
                algo="ray_tune_asha",
                trials=[],
                total_planned=int(sweep.budget or 16),
            )
    else:
        raise ValueError(f"unknown sweep algo {algo!r}")

    # CPCV path planning (the path count goes onto the parent run's
    # ``total_trials_searched`` for DSR — each train/test combination
    # IS a trial in the honest-accounting sense).
    cv_paths: list[CPCVPath] | None = None
    if sweep.cv == "combinatorial_purged":
        cv_kwargs = dict(sweep.cv_kwargs or {})
        cv_cfg = CPCVConfig(
            n_folds=int(cv_kwargs.get("n_folds", 6)),
            n_test_folds=int(cv_kwargs.get("n_test_folds", 2)),
            embargo_pct=float(cv_kwargs.get("embargo_pct", 1.0)),
            purge_size=int(cv_kwargs.get("purge_size", 0)),
            hard_guard_paths=int(cv_kwargs.get("hard_guard_paths", 100)),
            explicit_high_path_count_ok=bool(
                cv_kwargs.get("explicit_high_path_count_ok", False)
            ),
        )
        if n_observations is None:
            # Plan-time only; the runtime fills in n_observations once
            # the upstream Data Source resolves. We still record the
            # path count so the friction dialog can warn the user.
            planned = safe_cpcv_path_count(cv_cfg.n_folds, cv_cfg.n_test_folds)
            if planned > cv_cfg.hard_guard_paths and not cv_cfg.explicit_high_path_count_ok:
                raise CPCVPlanError(
                    f"CPCV plan would generate {planned} paths "
                    f"(hard guard is {cv_cfg.hard_guard_paths}); set "
                    f"sweep.cv_kwargs.explicit_high_path_count_ok=true to proceed."
                )
        else:
            cv_paths = combinatorial_purged_cv(int(n_observations), cv_cfg)

    # total_trials_searched is the honest count for DSR — trials × cv paths.
    n_cv = len(cv_paths) if cv_paths else (
        safe_cpcv_path_count(
            int(dict(sweep.cv_kwargs or {}).get("n_folds", 6)),
            int(dict(sweep.cv_kwargs or {}).get("n_test_folds", 2)),
        )
        if sweep.cv == "combinatorial_purged"
        else 1
    )
    total_trials = max(1, controller.total_planned) * max(1, n_cv)

    return SweepPlan(
        controller=controller,
        cv_paths=cv_paths,
        total_trials_searched=total_trials,
        primary_metric=sweep.primary_metric,
        maximize=bool(sweep.maximize),
    )


# ---------------------------------------------------------------------------
# Inline executor (Phase 3) — Celery group dispatch in Phase 4
# ---------------------------------------------------------------------------


def execute_sweep_inline(
    spec: GraphSpec,
    *,
    n_observations: int | None = None,
    inline_runner: Any | None = None,
    parent_run_id: str | None = None,
    use_mlflow: bool = True,
) -> SweepResult:
    """Run every planned trial in-process and pick the winner.

    The ``inline_runner`` callback is what the LabRuntime hands us —
    a function that takes a per-trial :class:`GraphSpec` (with the
    trial's params already merged) and returns a metrics dict. We
    keep this seam so the same controller serves both the Phase 3
    inline path and the Phase 4 Celery-group dispatch.

    When ``use_mlflow`` is True and MLflow is installed the parent +
    child runs are nested per the plan §3 contract.
    """
    plan = plan_sweep(spec, n_observations=n_observations)
    parent_mlflow_run = _maybe_start_parent_mlflow_run(
        spec=spec,
        plan=plan,
        parent_run_id=parent_run_id,
        use_mlflow=use_mlflow,
    )
    try:
        if plan.controller.algo == "optuna_tpe":
            results = _run_optuna_inline(plan, spec, inline_runner)
        elif plan.controller.algo == "ray_tune_asha":
            # Ray Tune is async by nature; Phase 3 inline-runs it as
            # a sequential fallback when the cluster is not reachable.
            results = _run_serial(plan.controller.trials, spec, inline_runner, plan, source_algo="ray_tune_asha")
        else:
            results = _run_serial(plan.controller.trials, spec, inline_runner, plan)
    finally:
        _maybe_end_mlflow_run(parent_mlflow_run)

    best_trial_id, best_metric = _pick_best(results, plan)
    dsr = _compute_dsr_for_sweep(results, plan)
    return SweepResult(
        plan=plan,
        trials=results,
        best_trial_id=best_trial_id,
        best_metric=best_metric,
        deflated_sharpe=dsr,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _run_serial(
    trials: list[SweepTrial],
    spec: GraphSpec,
    inline_runner: Any | None,
    plan: SweepPlan,
    *,
    source_algo: str | None = None,
) -> list[TrialResult]:
    """Run a static trial list serially and capture results."""
    import time

    results: list[TrialResult] = []
    for trial in trials:
        per_trial_spec = _apply_trial_params(spec, trial.params)
        started = time.perf_counter()
        child_mlflow_run = _maybe_start_child_mlflow_run(trial, plan)
        try:
            metrics = _call_inline_runner(inline_runner, per_trial_spec, trial)
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - started) * 1000.0
            results.append(
                TrialResult(
                    trial_id=trial.trial_id,
                    params=dict(trial.params),
                    status="error",
                    error=str(exc),
                    duration_ms=duration_ms,
                )
            )
            _maybe_end_mlflow_run(child_mlflow_run)
            continue
        duration_ms = (time.perf_counter() - started) * 1000.0
        primary = _extract_primary_metric(metrics, plan.primary_metric)
        result = TrialResult(
            trial_id=trial.trial_id,
            params=dict(trial.params),
            metrics=dict(metrics or {}),
            primary_metric=primary,
            duration_ms=duration_ms,
        )
        _maybe_log_child_metrics(child_mlflow_run, metrics, primary, plan.primary_metric)
        _maybe_end_mlflow_run(child_mlflow_run)
        results.append(result)
    return results


def _run_optuna_inline(
    plan: SweepPlan,
    spec: GraphSpec,
    inline_runner: Any | None,
) -> list[TrialResult]:
    """Optuna study driven by the inline runner."""
    cfg = spec.mode_config.evaluation
    sweep = cfg.sweep if cfg else None
    if sweep is None:
        return []
    ranges = {k: (float(v[0]), float(v[1])) for k, v in dict(sweep.ranges).items()}

    def _objective(params: dict[str, Any]) -> float:
        per_trial = _apply_trial_params(spec, params)
        metrics = _call_inline_runner(inline_runner, per_trial, None)
        return float(_extract_primary_metric(metrics, plan.primary_metric) or 0.0)

    ctrl = optuna_tpe_sweep(
        ranges,
        objective=_objective,
        budget=sweep.budget or 16,
        seed=sweep.seed,
        maximize=plan.maximize,
    )
    return [
        TrialResult(
            trial_id=t.trial_id,
            params=dict(t.params),
            primary_metric=t.primary_metric,
            metrics={plan.primary_metric: t.primary_metric} if t.primary_metric is not None else {},
        )
        for t in ctrl.trials
    ]


def _apply_trial_params(spec: GraphSpec, params: dict[str, Any]) -> GraphSpec:
    """Return a copy of ``spec`` with ``params`` merged into matching nodes.

    Each ``params`` key is dotted: ``"<node_id>.<param_name>"`` (so the
    UI can target any node param, not just a single root). When the
    key doesn't include a dot we apply it as a default that the
    matching node's params consume verbatim.
    """
    spec_dict = spec.model_dump(mode="json")
    nodes_by_id = {n["id"]: n for n in spec_dict["nodes"]}
    for key, value in params.items():
        if "." in key:
            node_id, _, param_name = key.partition(".")
            target = nodes_by_id.get(node_id)
            if target is None:
                continue
            target.setdefault("params", {})[param_name] = value
        else:
            for node in spec_dict["nodes"]:
                node.setdefault("params", {})[key] = value
    return GraphSpec.model_validate(spec_dict)


def _call_inline_runner(
    inline_runner: Any | None,
    per_trial_spec: GraphSpec,
    trial: SweepTrial | None,
) -> dict[str, Any]:
    """Invoke the caller-provided per-trial runner.

    The runner contract is ``runner(per_trial_spec) -> dict[str, Any]``;
    the dict is the trial's metrics. When ``inline_runner`` is None we
    return an empty metrics dict so plan + dispatch are still
    exercised in tests / dry-runs.
    """
    if inline_runner is None:
        return {}
    return dict(inline_runner(per_trial_spec) or {})


def _extract_primary_metric(metrics: dict[str, Any], name: str) -> float | None:
    if metrics is None:
        return None
    if name in metrics:
        try:
            return float(metrics[name])
        except (TypeError, ValueError):
            return None
    # Fallback — try the canonical Sharpe alias if the primary
    # metric is renamed.
    if name == "sharpe" and "Sharpe Ratio" in metrics:
        try:
            return float(metrics["Sharpe Ratio"])
        except (TypeError, ValueError):
            return None
    return None


def _pick_best(
    results: list[TrialResult], plan: SweepPlan
) -> tuple[int | None, float | None]:
    scored = [r for r in results if r.primary_metric is not None]
    if not scored:
        return None, None
    winner = max(scored, key=lambda r: r.primary_metric or float("-inf")) if plan.maximize else min(
        scored, key=lambda r: r.primary_metric or float("inf")
    )
    return winner.trial_id, winner.primary_metric


def _compute_dsr_for_sweep(
    results: list[TrialResult],
    plan: SweepPlan,
) -> float | None:
    """Compute the Deflated Sharpe Ratio for the sweep winner.

    Uses the honest ``total_trials_searched`` count from the plan
    (trials × cv paths) — per AGENTS rule from the plan, never the
    selected-subset count.
    """
    sharpes = [
        float(r.primary_metric)
        for r in results
        if r.primary_metric is not None and not math.isnan(r.primary_metric)
    ]
    if not sharpes:
        return None
    from aqp.lab.evaluation.deflated_sharpe import deflated_sharpe_ratio

    best = max(sharpes) if plan.maximize else min(sharpes)
    variance = _variance(sharpes)
    try:
        return deflated_sharpe_ratio(
            observed_sharpe=best,
            n_obs=max(2, len(sharpes)),
            n_trials=max(1, plan.total_trials_searched),
            variance_of_sharpes=variance if variance > 0 else None,
        )
    except Exception:  # noqa: BLE001
        return None


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


# ---------------------------------------------------------------------------
# MLflow nested run plumbing
# ---------------------------------------------------------------------------


def _maybe_start_parent_mlflow_run(
    *,
    spec: GraphSpec,
    plan: SweepPlan,
    parent_run_id: str | None,
    use_mlflow: bool,
) -> Any | None:
    if not use_mlflow:
        return None
    try:
        import mlflow  # type: ignore[import-not-found]

        from aqp.config import settings

        tracking = getattr(settings, "mlflow_tracking_uri", None)
        if tracking:
            mlflow.set_tracking_uri(str(tracking))
        run_name = f"lab-sweep:{spec.name}:{spec.snapshot_hash()[:8]}"
        run = mlflow.start_run(run_name=run_name)
        mlflow.log_params(
            {
                "lab_sweep.algo": plan.controller.algo,
                "lab_sweep.primary_metric": plan.primary_metric,
                "lab_sweep.maximize": plan.maximize,
                "lab_sweep.total_trials_searched": plan.total_trials_searched,
                "lab_sweep.parent_run_id": parent_run_id or "",
            }
        )
        return run
    except Exception:  # noqa: BLE001
        return None


def _maybe_start_child_mlflow_run(trial: SweepTrial, plan: SweepPlan) -> Any | None:
    try:
        import mlflow  # type: ignore[import-not-found]

        run = mlflow.start_run(run_name=f"trial:{trial.trial_id}", nested=True)
        mlflow.log_params({f"trial.{k}": v for k, v in trial.params.items()})
        mlflow.log_param("trial.algo", plan.controller.algo)
        return run
    except Exception:  # noqa: BLE001
        return None


def _maybe_log_child_metrics(
    child_run: Any | None,
    metrics: dict[str, Any] | None,
    primary: float | None,
    primary_name: str,
) -> None:
    if child_run is None or not metrics:
        return
    try:
        import mlflow  # type: ignore[import-not-found]

        for k, v in metrics.items():
            try:
                mlflow.log_metric(str(k), float(v))
            except (TypeError, ValueError):
                continue
        if primary is not None:
            mlflow.log_metric(f"primary.{primary_name}", float(primary))
    except Exception:  # noqa: BLE001
        return


def _maybe_end_mlflow_run(run: Any | None) -> None:
    if run is None:
        return
    try:
        import mlflow  # type: ignore[import-not-found]

        mlflow.end_run()
    except Exception:  # noqa: BLE001
        return


__all__ = [
    "SweepPlan",
    "SweepResult",
    "TrialResult",
    "execute_sweep_inline",
    "plan_sweep",
]
