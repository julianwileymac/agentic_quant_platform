"""Iterative parameter-mutation optimisation loop.

Phase 4 of the agentic platform overhaul. Implements the closed-loop
research cycle the report describes:

1. Read the latest :class:`BacktestRun` metrics for a strategy.
2. Look up the active regime via :class:`VIXPercentileRegimeClassifier`.
3. Query :func:`aqp.agents.strategy_memory.get_best_params` for warm
   starts.
4. Ask an :class:`AgentRuntime` mutator agent to propose a new
   parameter set.
5. Dispatch :func:`run_backtest_from_config` with the mutated params.
6. On completion, call :func:`record_observation` to grow the
   regime memory.
7. Stop when ``sharpe >= target`` or ``iteration >= max_iterations``.

The task is workspace-aware: it re-binds the request context inside
the Celery worker so every downstream chokepoint sees the right
tenancy stamp. Progress is emitted on the standard progress bus so
the SPA can render the iteration history live.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.auth.context import RequestContext
from aqp.auth.contextvars import use_context
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


_DEFAULT_MAX_ITERATIONS = 8


@celery_app.task(
    bind=True,
    name="aqp.tasks.optimization_tasks.iterate_until_target",
)
def iterate_until_target(
    self,
    *,
    strategy_id: str,
    base_config: dict[str, Any],
    target_sharpe: float,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    regime: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Run the param-mutation loop until target Sharpe is reached.

    ``base_config`` is the full backtest YAML (already validated by
    the route layer); the task mutates only the ``params`` section
    between iterations.

    Stops when:

    - The best Sharpe across iterations meets or exceeds
      ``target_sharpe``.
    - The iteration counter reaches ``max_iterations``.
    - The mutator agent returns the same params twice in a row
      (convergence — no further proposals).
    """
    task_id = self.request.id or "iterate_until_target"
    ctx = RequestContext(
        user_id=user_id or "",
        workspace_id=workspace_id,
        project_id=project_id,
        run_id=task_id,
    )
    history: list[dict[str, Any]] = []
    seen_param_hashes: set[str] = set()

    try:
        with use_context(ctx):
            from aqp.agents.strategy_memory import (
                _params_hash,
                get_best_params,
                record_observation,
                top_k_for_regime,
            )
            from aqp.backtest.runner import run_backtest_from_config

            current_config = dict(base_config)
            current_params = dict(current_config.get("params") or {})
            best_metrics: dict[str, Any] | None = None
            best_params: dict[str, Any] = current_params

            # Warm-start from regime memory if the caller supplied a regime.
            if regime:
                best_known = get_best_params(strategy_id, regime, ctx=ctx)
                if best_known and best_known.get("params"):
                    current_params = dict(best_known["params"])
                    current_config["params"] = current_params
                    emit(
                        task_id,
                        "warm_start",
                        f"Warm-starting from regime memory (sharpe={best_known.get('best_sharpe', 0):.3f})",
                        regime=regime,
                        params=current_params,
                    )

            for iteration in range(int(max_iterations)):
                phash = _params_hash(current_params)
                if phash in seen_param_hashes:
                    emit(task_id, "converged", "Mutator returned a previously seen params; stopping")
                    break
                seen_param_hashes.add(phash)

                emit(
                    task_id,
                    f"iteration_{iteration + 1}",
                    f"Running backtest iteration {iteration + 1}/{max_iterations}",
                    params=current_params,
                )
                run_result = run_backtest_from_config(current_config)
                metrics = {
                    "sharpe": float(run_result.get("sharpe", 0.0) or 0.0),
                    "sortino": float(run_result.get("sortino", 0.0) or 0.0),
                    "calmar": float(run_result.get("calmar", 0.0) or 0.0),
                    "max_drawdown": float(run_result.get("max_drawdown", 0.0) or 0.0),
                    "total_return": float(run_result.get("total_return", 0.0) or 0.0),
                }
                history.append(
                    {
                        "iteration": iteration + 1,
                        "params": current_params,
                        "metrics": metrics,
                        "run_id": run_result.get("run_id"),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                if regime:
                    try:
                        record_observation(
                            strategy_id=strategy_id,
                            regime=regime,
                            params=current_params,
                            metrics=metrics,
                            backtest_run_id=run_result.get("run_id"),
                            ctx=ctx,
                        )
                    except Exception:  # noqa: BLE001
                        logger.debug("record_observation failed; continuing", exc_info=True)

                if best_metrics is None or metrics["sharpe"] > float(best_metrics.get("sharpe", 0.0)):
                    best_metrics = metrics
                    best_params = dict(current_params)

                if metrics["sharpe"] >= float(target_sharpe):
                    emit(
                        task_id,
                        "target_met",
                        f"Sharpe {metrics['sharpe']:.3f} >= target {target_sharpe:.3f}",
                    )
                    break

                # Ask the mutator to propose new params for the next iteration.
                proposed = _mutate_params(
                    strategy_id=strategy_id,
                    history=history,
                    regime=regime,
                    target_sharpe=float(target_sharpe),
                    ctx=ctx,
                )
                if not proposed:
                    emit(task_id, "no_mutation", "Mutator returned no proposal; stopping early")
                    break
                current_params = dict(proposed)
                current_config["params"] = current_params

            payload = {
                "ok": True,
                "strategy_id": strategy_id,
                "regime": regime,
                "iterations": len(history),
                "history": history,
                "best_metrics": best_metrics or {},
                "best_params": best_params,
                "target_sharpe": float(target_sharpe),
                "target_met": bool(best_metrics and best_metrics.get("sharpe", 0.0) >= float(target_sharpe)),
            }
            emit_done(task_id, payload)
            return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("iterate_until_target failed")
        emit_error(task_id, str(exc))
        raise


def _mutate_params(
    *,
    strategy_id: str,
    history: list[dict[str, Any]],
    regime: str | None,
    target_sharpe: float,
    ctx: RequestContext,
) -> dict[str, Any] | None:
    """Ask the mutator :class:`AgentRuntime` to propose new parameters.

    The agent spec lives at ``configs/agents/parameter_mutator.yaml``
    (Phase 4 ships a default spec; the user can override per-bot).
    The runtime call is wrapped in a try/except so a missing spec or
    unreachable LLM gracefully degrades to a deterministic
    perturbation of the last params.
    """
    if not history:
        return None

    last = history[-1]
    last_params = dict(last.get("params") or {})
    try:
        from aqp.agents.runtime import AgentRuntime

        runtime = AgentRuntime()
        prompt_inputs = {
            "strategy_id": strategy_id,
            "regime": regime or "unknown",
            "target_sharpe": target_sharpe,
            "history": history[-3:],
        }
        result = runtime.run(spec_name="parameter_mutator", inputs=prompt_inputs, context=ctx)
        proposed = result.get("params") if isinstance(result, dict) else None
        if isinstance(proposed, dict) and proposed:
            return proposed
    except Exception:  # noqa: BLE001
        logger.debug("parameter_mutator agent failed; using deterministic fallback", exc_info=True)

    return _deterministic_perturbation(last_params)


def _deterministic_perturbation(params: dict[str, Any]) -> dict[str, Any]:
    """Fallback mutator: scale numeric params by a small jitter.

    Used when the LLM mutator is unreachable. Keeps the loop moving
    rather than dead-locking on a single set of params; the AgentQuant
    research showed even random perturbations beat the static baseline.
    """
    import random

    rng = random.Random(0xA0B0C0D0)
    out: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, int):
            delta = max(1, abs(value) // 5)
            out[key] = value + rng.randint(-delta, delta)
        elif isinstance(value, float):
            out[key] = float(value) * rng.uniform(0.85, 1.15)
        else:
            out[key] = value
    return out
