"""Reinforcement-learning layer — FinRL + FinRobot inspired refactor.

Public surface:

- :mod:`aqp.rl.core` — abstract bases (env, observation, action, reward,
  termination, policy, agent, data pipeline, ensembler, experiment,
  trajectory store) plus the :class:`RLComponent` metaclass that
  auto-registers every concrete subclass.
- :mod:`aqp.rl.spec` — :class:`RLExperimentSpec` declarative blueprint.
- :mod:`aqp.rl.runtime` — :class:`RLRuntime` single sanctioned executor.
- :mod:`aqp.rl.envs` — concrete envs (existing AQP envs + FinRL ports +
  options / execution / market-making placeholders).
- :mod:`aqp.rl.rewards`, :mod:`aqp.rl.observations`, :mod:`aqp.rl.actions`,
  :mod:`aqp.rl.terminations` — composable component libraries.
- :mod:`aqp.rl.data_pipelines` — Iceberg / Yahoo / Alpaca / streaming /
  replay data pipelines (FinRL ``DataProcessor`` parity).
- :mod:`aqp.rl.agents` — SB3 / ElegantRL / RLlib / CleanRL / LLM-hybrid
  adapters + classical / Q-family / actor-critic / evolutionary / SPM.
- :mod:`aqp.rl.ensemblers` / :mod:`aqp.rl.experiments` /
  :mod:`aqp.rl.applications` — high-level orchestration.
- :mod:`aqp.rl.trajectories` — Iceberg-backed trajectory store + DuckDB views.

Importing this module triggers eager registration of the concrete
component libraries so the introspection routes
(``GET /rl/components``) light up without scanning the filesystem.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp.rl.agents.sb3_adapter import SB3Adapter
from aqp.rl.envs.portfolio_env import PortfolioAllocationEnv
from aqp.rl.envs.stock_trading_env import StockTradingEnv
from aqp.rl.evaluator import evaluate_policy
from aqp.rl.runtime import RLRuntime, RLRunResult, runtime_for
from aqp.rl.spec import RLExperimentSpec
from aqp.rl.trainer import train_from_config

# Eager imports so the metaclass registers every component on first
# ``aqp.rl`` import. Each is wrapped to keep optional deps optional.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import actions, observations, rewards, terminations  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import data_pipelines  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import ensemblers, experiments  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import envs  # noqa: F401
# Hybrid agentic-RL Phase 2 + Phase 3: eager-import the new
# advantage estimators + policy backbones so the RLComponent
# metaclass auto-registration fires and `/rl/components/{kind}`
# enumerates them.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import advantage  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import policies  # noqa: F401
# Hybrid agentic-RL Phase 1: eager-import the weight-centric
# portfolio pipeline + RL ↔ Backtest bridge so RLBacktestEnv and
# the WeightCentricPipeline are reachable via build_from_config.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import portfolio  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl import bridges  # noqa: F401
with _contextlib.suppress(Exception):
    from aqp.rl.tagging import apply_tags as _apply_rl_tags

    _apply_rl_tags()

__all__ = [
    "PortfolioAllocationEnv",
    "RLExperimentSpec",
    "RLRunResult",
    "RLRuntime",
    "SB3Adapter",
    "StockTradingEnv",
    "evaluate_policy",
    "runtime_for",
    "train_from_config",
]
