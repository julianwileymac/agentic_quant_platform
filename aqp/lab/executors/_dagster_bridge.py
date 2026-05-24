"""Dagster sandbox bridge for Simulation-mode runs.

Phase 4 packages a :class:`GraphSpec` + :class:`SimulationConfig`
into a Dagster sandbox job specification per AGENTS rule 32:

- One session = one tempdir = one Redis namespace
  ``aqp:sandbox:<session_id>:*``.
- The :class:`SandboxRuntime` (from :mod:`aqp.dagster.sandbox.runtime`)
  owns lifecycle / janitor / Redis isolation.
- The bridge here is intentionally thin — it translates Lab vocabulary
  (``env``, ``capital``, ``latency_ns``, ``speed``, ``extras``) into
  the Dagster job's run config and returns a serialisable handle
  the Lab can pin on ``LabRun.dagster_run_id`` for follow-up.

Inline fallback: when the Dagster runtime is unavailable (dev, tests,
or operator hasn't installed pyspark / hftbacktest yet) we run the
sub-mode runner SYNCHRONOUSLY in-process and emit a synthetic
``dagster_run_id`` so the rest of the contract is exercised. This
mirrors the LabRuntime's general philosophy: never block on optional
deps; surface clear actionable errors when something only works in
prod.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from aqp.lab.schema import GraphSpec, SimulationConfig

logger = logging.getLogger(__name__)


@dataclass
class SandboxHandle:
    """What the LabRuntime pins on ``LabRun.dagster_run_id``."""

    dagster_run_id: str
    sandbox_session_id: str
    env: str
    inline_fallback: bool
    payload: dict[str, Any]


def submit_simulation(
    spec: GraphSpec,
    sim_cfg: SimulationConfig,
    *,
    session_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
) -> tuple[SandboxHandle, dict[str, Any]]:
    """Submit a Simulation-mode run to the Dagster sandbox runtime.

    Returns ``(SandboxHandle, run_summary)``. The summary contains
    the synchronous-fallback metrics when Dagster is unavailable;
    when Dagster IS reachable the summary is a sentinel + the
    handle points at the Dagster run id for streaming follow-up.
    """
    sandbox_session_id = session_id or f"lab-sim-{uuid4().hex[:10]}"
    env = sim_cfg.env

    sandbox_payload = _build_sandbox_payload(
        spec=spec,
        sim_cfg=sim_cfg,
        run_id=run_id,
        task_id=task_id,
    )

    sandbox = _maybe_load_sandbox_runtime()
    if sandbox is None:
        # Inline fallback — run the sub-mode runner directly and stash
        # a synthetic dagster_run_id so the LabRun row still has a
        # pointer to "this is the simulation run".
        summary = _run_inline(env=env, spec=spec, sim_cfg=sim_cfg)
        return (
            SandboxHandle(
                dagster_run_id=f"inline-{uuid4().hex[:10]}",
                sandbox_session_id=sandbox_session_id,
                env=env,
                inline_fallback=True,
                payload=sandbox_payload,
            ),
            summary,
        )

    # Real Dagster path — package the spec + sim_cfg as a job run.
    try:
        dagster_run_id = sandbox.submit_lab_simulation(  # type: ignore[attr-defined]
            session_id=sandbox_session_id,
            graph_id=getattr(spec, "name", "unnamed"),
            env=env,
            payload=sandbox_payload,
        )
    except AttributeError:
        # Older SandboxRuntime doesn't expose submit_lab_simulation
        # yet — fall back to inline run + emit a sentinel handle.
        summary = _run_inline(env=env, spec=spec, sim_cfg=sim_cfg)
        return (
            SandboxHandle(
                dagster_run_id=f"inline-{uuid4().hex[:10]}",
                sandbox_session_id=sandbox_session_id,
                env=env,
                inline_fallback=True,
                payload=sandbox_payload,
            ),
            summary,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("SandboxRuntime.submit_lab_simulation failed: %s", exc)
        summary = _run_inline(env=env, spec=spec, sim_cfg=sim_cfg)
        return (
            SandboxHandle(
                dagster_run_id=f"inline-{uuid4().hex[:10]}",
                sandbox_session_id=sandbox_session_id,
                env=env,
                inline_fallback=True,
                payload={**sandbox_payload, "submit_error": str(exc)},
            ),
            summary,
        )

    return (
        SandboxHandle(
            dagster_run_id=str(dagster_run_id),
            sandbox_session_id=sandbox_session_id,
            env=env,
            inline_fallback=False,
            payload=sandbox_payload,
        ),
        {
            "status": "queued",
            "env": env,
            "dagster_run_id": dagster_run_id,
        },
    )


def _build_sandbox_payload(
    *,
    spec: GraphSpec,
    sim_cfg: SimulationConfig,
    run_id: str | None,
    task_id: str | None,
) -> dict[str, Any]:
    return {
        "graph_name": spec.name,
        "content_hash": spec.snapshot_hash(),
        "env": sim_cfg.env,
        "seed": sim_cfg.seed,
        "speed": sim_cfg.speed,
        "capital": sim_cfg.capital,
        "fee_bps": sim_cfg.fee_bps,
        "latency_ns": sim_cfg.latency_ns,
        "extras": dict(sim_cfg.extras or {}),
        "run_id": run_id,
        "task_id": task_id,
    }


def _maybe_load_sandbox_runtime() -> Any | None:
    try:
        from aqp.dagster.sandbox.runtime import SandboxRuntime  # type: ignore[import-not-found]

        return SandboxRuntime()
    except Exception:  # noqa: BLE001
        return None


def _run_inline(*, env: str, spec: GraphSpec, sim_cfg: SimulationConfig) -> dict[str, Any]:
    """Dispatch the requested simulation env synchronously when Dagster is missing."""
    started = time.perf_counter()
    payload = _build_sandbox_payload(
        spec=spec, sim_cfg=sim_cfg, run_id=None, task_id=None
    )
    try:
        if env == "stochastic":
            from aqp.lab.simulation.stochastic import run_stochastic_simulation

            result = run_stochastic_simulation(payload)
        elif env == "hftbt":
            from aqp.lab.simulation.hftbt import run_hftbt_simulation

            result = run_hftbt_simulation(payload, spec=spec)
        elif env == "rl":
            from aqp.lab.simulation.rl_env import run_rl_simulation

            result = run_rl_simulation(payload, spec=spec)
        elif env == "optctl":
            from aqp.lab.simulation.optctl import run_optctl_simulation

            result = run_optctl_simulation(payload, spec=spec)
        else:
            result = {
                "status": "error",
                "env": env,
                "error": f"unknown simulation env {env!r}",
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("inline simulation env=%s crashed", env)
        result = {"status": "error", "env": env, "error": str(exc)}
    result.setdefault("duration_ms", (time.perf_counter() - started) * 1000.0)
    return result


__all__ = ["SandboxHandle", "submit_simulation"]
