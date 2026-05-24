"""``env='rl'`` simulation runner — routes through :class:`RLRuntime`.

Phase 4 wires a Simulation-mode RL run as a thin wrapper around
:func:`RLRuntime.train` (default) / ``.evaluate`` / ``.paper`` /
``.replay`` / ``.walk_forward`` per AGENTS rule 16. The spec is
resolved from either:

- An inline ``extras['spec']`` (the Simulation panel's "draft" path),
- An ``extras['spec_name']`` lookup against
  :func:`aqp.rl.registry.get_rl_spec`,
- Or the first ``model.rl`` node on the supplied :class:`GraphSpec`.

The runner emits a ``sim.tick`` envelope with ``kind="rl.train_step"``
per training step when the runtime exposes a progress hook (the
existing RLRuntime emits canonical progress frames via
:mod:`aqp.tasks._progress` — the WS bus already forwards these so
no extra plumbing is needed here).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.lab.schema import GraphSpec

logger = logging.getLogger(__name__)


def run_rl_simulation(
    payload: dict[str, Any], *, spec: GraphSpec | None = None
) -> dict[str, Any]:
    started = time.time()
    extras = dict(payload.get("extras") or {})
    action = str(extras.get("action") or "train").lower()
    inline_spec = extras.get("spec")
    spec_name = extras.get("spec_name")
    overrides = dict(extras.get("overrides") or {})
    checkpoint = extras.get("checkpoint")

    if spec is not None and inline_spec is None and not spec_name:
        for node in spec.nodes:
            if node.type == "model.rl":
                inline_spec = (node.params or {}).get("spec")
                spec_name = (node.params or {}).get("spec_name")
                if action == "train":
                    action = str((node.params or {}).get("action") or "train").lower()
                overrides = dict((node.params or {}).get("overrides") or overrides or {})
                checkpoint = checkpoint or (node.params or {}).get("checkpoint")
                break

    if not inline_spec and not spec_name:
        return {
            "status": "error",
            "env": "rl",
            "error": (
                "rl simulation requires either SimulationConfig.extras.spec / spec_name "
                "or a model.rl node on the graph"
            ),
            "duration_ms": (time.time() - started) * 1000.0,
        }

    try:
        from aqp.rl.runtime import RLRuntime
        from aqp.rl.spec import RLExperimentSpec
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "env": "rl",
            "error": f"RLRuntime surface unavailable: {exc}",
            "duration_ms": (time.time() - started) * 1000.0,
        }

    if inline_spec:
        try:
            rl_spec = RLExperimentSpec.model_validate(inline_spec)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "env": "rl",
                "error": f"inline spec validation failed: {exc}",
                "duration_ms": (time.time() - started) * 1000.0,
            }
    else:
        try:
            from aqp.rl.registry import get_rl_spec

            rl_spec = get_rl_spec(str(spec_name))
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "env": "rl",
                "error": f"spec lookup for {spec_name!r} failed: {exc}",
                "duration_ms": (time.time() - started) * 1000.0,
            }

    runtime = RLRuntime(rl_spec)
    try:
        if action == "train":
            result = runtime.train(overrides=overrides)
        elif action == "evaluate":
            if not checkpoint:
                return {
                    "status": "error",
                    "env": "rl",
                    "error": "rl(action=evaluate) requires checkpoint",
                    "duration_ms": (time.time() - started) * 1000.0,
                }
            result = runtime.evaluate(checkpoint=str(checkpoint), overrides=overrides)
        elif action == "paper":
            if not checkpoint:
                return {
                    "status": "error",
                    "env": "rl",
                    "error": "rl(action=paper) requires checkpoint",
                    "duration_ms": (time.time() - started) * 1000.0,
                }
            result = runtime.paper(checkpoint=str(checkpoint), overrides=overrides)
        elif action == "replay":
            if not checkpoint:
                return {
                    "status": "error",
                    "env": "rl",
                    "error": "rl(action=replay) requires checkpoint",
                    "duration_ms": (time.time() - started) * 1000.0,
                }
            result = runtime.replay(checkpoint=str(checkpoint), new_window=overrides or None)
        elif action == "walk_forward":
            result = runtime.walk_forward(overrides=overrides)
        else:
            return {
                "status": "error",
                "env": "rl",
                "error": f"unknown rl action {action!r}",
                "duration_ms": (time.time() - started) * 1000.0,
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("rl simulation failed action=%s", action)
        return {
            "status": "error",
            "env": "rl",
            "error": str(exc),
            "duration_ms": (time.time() - started) * 1000.0,
        }

    metrics = dict(getattr(result, "metrics", {}) or {})
    return {
        "status": getattr(result, "status", "done") or "done",
        "env": "rl",
        "action": action,
        "spec_name": rl_spec.name,
        "rl_run_id": getattr(result, "run_id", None),
        "checkpoint_uri": getattr(result, "checkpoint_uri", None),
        "metrics": metrics,
        "duration_ms": (time.time() - started) * 1000.0,
    }


__all__ = ["run_rl_simulation"]
