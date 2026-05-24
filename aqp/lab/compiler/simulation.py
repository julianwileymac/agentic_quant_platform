"""Simulation-mode compiler: GraphSpec → Dagster sandbox job description.

Phase 4 wires the four sim sub-modes (``hftbt`` / ``stochastic`` /
``rl`` / ``optctl``) into a single payload the
:class:`SandboxRuntime`-style launcher can hand to the matching
executor.

Each sub-mode resolves a backing primitive that already lives in
the AQP runtime tree (no new dependencies):

- ``hftbt`` → ``aqp.backtest.hft.LobBacktestEngine``
- ``stochastic`` → ``aqp.lab.executors.math_gbm`` / friends (JAX
  vmap'd path simulator already shipped in Phase 3)
- ``rl`` → ``aqp.rl.runtime.RLRuntime`` (AGENTS rule 16 — never
  call ``agent.train`` directly)
- ``optctl`` → ``aqp.optimal_control.{avellaneda_stoikov,
  cartea_jaimungal, obizhaeva_wang}`` quote_fn factories,
  with the optional hftbt LOB loop wiring for closed-loop runs.
"""
from __future__ import annotations

from typing import Any

from aqp.lab.compiler import CompileContext, CompileResult
from aqp.lab.schema import GraphSpec, SimulationConfig


SIM_ENV_EXECUTORS: dict[str, str] = {
    "hftbt": "aqp.lab.simulation.hftbt:run_hftbt_simulation",
    "stochastic": "aqp.lab.simulation.stochastic:run_stochastic_simulation",
    "rl": "aqp.lab.simulation.rl_env:run_rl_simulation",
    "optctl": "aqp.lab.simulation.optctl:run_optctl_simulation",
}


def compile_simulation(spec: GraphSpec, ctx: CompileContext) -> CompileResult:
    if spec.mode != "simulation":
        raise ValueError(
            f"compile_simulation requires mode='simulation', got {spec.mode!r}"
        )
    sim_cfg = spec.mode_config.simulation or SimulationConfig()
    env = (sim_cfg.env or "hftbt").lower()
    executor_path = SIM_ENV_EXECUTORS.get(env)
    if executor_path is None:
        raise ValueError(
            f"simulation: unknown env {env!r} (expected one of {list(SIM_ENV_EXECUTORS)})"
        )

    payload: dict[str, Any] = {
        "run_id": ctx.run_id,
        "task_id": ctx.task_id,
        "session_id": ctx.session_id,
        "lab_id": ctx.lab_id,
        "env": env,
        "executor": executor_path,
        "seed": sim_cfg.seed,
        "speed": sim_cfg.speed,
        "capital": sim_cfg.capital,
        "fee_bps": sim_cfg.fee_bps,
        "latency_ns": sim_cfg.latency_ns,
        "extras": dict(sim_cfg.extras or {}),
        "node_ids": [n.id for n in spec.nodes],
    }
    return CompileResult(
        mode="simulation",
        target="dagster_job",
        payload=payload,
        breadcrumbs=[
            {
                "compiler": "simulation",
                "env": env,
                "executor": executor_path,
                "seed": sim_cfg.seed,
            }
        ],
    )


__all__ = ["SIM_ENV_EXECUTORS", "compile_simulation"]
