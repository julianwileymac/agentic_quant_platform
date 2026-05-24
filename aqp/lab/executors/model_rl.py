"""``model.rl`` — train / evaluate an RL spec through :class:`RLRuntime`.

Routes EVERY action through :class:`aqp.rl.runtime.RLRuntime` per
AGENTS rule 16. The executor never calls ``agent.train`` /
``agent.evaluate`` / ``policy.predict`` directly — it constructs (or
loads) an :class:`RLExperimentSpec` and lets the runtime drive
training, hash-locked spec snapshotting, MLflow autolog, and
Iceberg trajectory persistence.

Two invocation modes:

1. ``params.spec_name`` — reuse a persisted ``RLExperimentSpec`` (the
   normal flow). The runtime resolves the latest version from
   ``rl_experiment_versions``.
2. ``params.spec`` — inline spec dict (used by the Lab "draft" path
   when the user is iterating on env / reward / agent configuration
   without writing it back to disk first).

Lifecycle:

- ``params.action`` ∈ ``{"train","evaluate","paper","replay","walk_forward"}``,
  default ``"train"``.
- ``params.checkpoint`` — required for ``evaluate``/``paper``/``replay``.
- ``params.run_name`` / ``params.overrides`` are forwarded verbatim
  to the matching runtime method.

The trained policy + the resulting :class:`RLRunResult` land on the
output_locator so a downstream ``out.publish_mlflow`` node can
register the artifact, and ``sim.tick`` consumers (Phase 4) can
attach to the same run id.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"train", "evaluate", "paper", "replay", "walk_forward"}


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    action = str(params.get("action") or "train").lower()
    if action not in _VALID_ACTIONS:
        return NodeResult(
            status="error",
            error=f"model.rl: unknown action {action!r}; valid {sorted(_VALID_ACTIONS)}",
            log_label="model.rl:bad_action",
        )

    spec_name = params.get("spec_name")
    inline_spec = params.get("spec")
    if not spec_name and not inline_spec:
        return NodeResult(
            status="error",
            error="model.rl requires either params.spec_name or params.spec",
            log_label="model.rl:missing_spec",
        )

    try:
        from aqp.rl.runtime import RLRuntime
        from aqp.rl.spec import RLExperimentSpec
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"RLRuntime surface unavailable: {exc}",
            log_label="model.rl:import_fail",
        )

    spec: RLExperimentSpec
    if inline_spec:
        try:
            spec = RLExperimentSpec.model_validate(inline_spec)
        except Exception as exc:  # noqa: BLE001
            return NodeResult(
                status="error",
                error=f"model.rl: inline spec validation failed: {exc}",
                log_label="model.rl:bad_inline_spec",
            )
    else:
        try:
            from aqp.rl.registry import get_rl_spec
        except Exception as exc:  # noqa: BLE001
            return NodeResult(
                status="error",
                error=f"could not import aqp.rl.registry: {exc}",
                log_label="model.rl:registry_import_fail",
            )
        try:
            spec = get_rl_spec(str(spec_name))
        except Exception as exc:  # noqa: BLE001
            return NodeResult(
                status="error",
                error=f"model.rl: spec lookup for {spec_name!r} failed: {exc}",
                log_label="model.rl:spec_lookup_fail",
            )

    runtime = RLRuntime(
        spec,
        run_id=None,
        task_id=ctx.task_id,
        context=ctx.request_context,
    )
    overrides = params.get("overrides") or {}
    if not isinstance(overrides, dict):
        return NodeResult(
            status="error",
            error="model.rl: params.overrides must be a dict",
            log_label="model.rl:bad_overrides",
        )

    try:
        if action == "train":
            result = runtime.train(
                run_name=params.get("run_name"),
                overrides=overrides,
            )
        elif action == "evaluate":
            checkpoint = params.get("checkpoint")
            if not checkpoint:
                return NodeResult(
                    status="error",
                    error="model.rl(action=evaluate) requires params.checkpoint",
                    log_label="model.rl:missing_checkpoint",
                )
            result = runtime.evaluate(checkpoint=str(checkpoint), overrides=overrides)
        elif action == "paper":
            checkpoint = params.get("checkpoint")
            if not checkpoint:
                return NodeResult(
                    status="error",
                    error="model.rl(action=paper) requires params.checkpoint",
                    log_label="model.rl:missing_checkpoint",
                )
            result = runtime.paper(checkpoint=str(checkpoint), overrides=overrides)
        elif action == "replay":
            checkpoint = params.get("checkpoint")
            if not checkpoint:
                return NodeResult(
                    status="error",
                    error="model.rl(action=replay) requires params.checkpoint",
                    log_label="model.rl:missing_checkpoint",
                )
            result = runtime.replay(
                checkpoint=str(checkpoint),
                new_window=overrides if overrides else None,
            )
        elif action == "walk_forward":
            result = runtime.walk_forward(overrides=overrides)
        else:  # defensive — _VALID_ACTIONS guarded above
            return NodeResult(
                status="error",
                error=f"model.rl: unreachable action {action!r}",
                log_label="model.rl:unreachable",
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("model.rl runtime call failed (action=%s)", action)
        return NodeResult(
            status="error",
            error=f"RLRuntime.{action}() failed: {exc}",
            log_label=f"model.rl:{action}:fail",
        )

    metrics = dict(getattr(result, "metrics", {}) or {})
    if isinstance(result, dict):
        metrics = dict(result.get("metrics") or {})
        run_id = result.get("run_id")
        status = result.get("status") or "done"
        error = result.get("error")
        checkpoint_uri = result.get("checkpoint_uri")
    else:
        run_id = getattr(result, "run_id", None)
        status = getattr(result, "status", "done") or "done"
        error = getattr(result, "error", None)
        checkpoint_uri = getattr(result, "checkpoint_uri", None)

    return NodeResult(
        status="error" if status == "error" else "done",
        output_locator={
            "kind": "rl_run",
            "action": action,
            "rl_run_id": run_id,
            "checkpoint_uri": checkpoint_uri,
            "spec_name": spec.name,
            "node_id": node.id,
        },
        metrics={
            "action": action,
            **{str(k): _coerce_float(v) for k, v in (metrics or {}).items()},
        },
        error=str(error) if (status == "error" and error) else None,
        log_label=f"model.rl:{action}:{spec.slug or spec.name}",
    )


def _coerce_float(value: Any) -> Any:
    if isinstance(value, (int, float, bool)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


__all__ = ["execute"]
