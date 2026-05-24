"""Simulation-mode sub-runners (hftbt / stochastic / rl / optctl).

Each module ships a single :func:`run_*_simulation(payload, runtime)`
callable that the Dagster sandbox launcher invokes. The runners wrap
existing AQP primitives — they never re-implement the engines.
"""
from __future__ import annotations

from aqp.lab.simulation.hftbt import run_hftbt_simulation
from aqp.lab.simulation.optctl import run_optctl_simulation
from aqp.lab.simulation.rl_env import run_rl_simulation
from aqp.lab.simulation.stochastic import run_stochastic_simulation

__all__ = [
    "run_hftbt_simulation",
    "run_optctl_simulation",
    "run_rl_simulation",
    "run_stochastic_simulation",
]
