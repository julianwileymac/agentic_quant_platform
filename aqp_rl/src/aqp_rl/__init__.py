"""Reinforcement-learning layer — FinRL + FinRobot inspired refactor.

Public surface:

- :mod:`aqp_rl.core` — abstract bases (env, observation, action, reward,
  termination, policy, agent, data pipeline, ensembler, experiment,
  trajectory store) plus the :class:`RLComponent` metaclass that
  auto-registers every concrete subclass.
- :mod:`aqp_rl.spec` — :class:`RLExperimentSpec` declarative blueprint.
- :mod:`aqp_rl.runtime` — :class:`RLRuntime` single sanctioned executor.
- :mod:`aqp_rl.envs` — concrete envs (existing AQP envs + FinRL ports +
  options / execution / market-making placeholders).
- :mod:`aqp_rl.rewards`, :mod:`aqp_rl.observations`, :mod:`aqp_rl.actions`,
  :mod:`aqp_rl.terminations` — composable component libraries.
- :mod:`aqp_rl.data_pipelines` — Iceberg / Yahoo / Alpaca / streaming /
  replay data pipelines (FinRL ``DataProcessor`` parity).
- :mod:`aqp_rl.agents` — SB3 / ElegantRL / RLlib / CleanRL / LLM-hybrid
  adapters + classical / Q-family / actor-critic / evolutionary / SPM.
- :mod:`aqp_rl.ensemblers` / :mod:`aqp_rl.experiments` /
  :mod:`aqp_rl.applications` — high-level orchestration.
- :mod:`aqp_rl.trajectories` — Iceberg-backed trajectory store + DuckDB views.

Importing this module triggers eager registration of the concrete
component libraries so the introspection routes
(``GET /rl/components``) light up without scanning the filesystem.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp_rl.agents.sb3_adapter import SB3Adapter
from aqp_rl.envs.portfolio_env import PortfolioAllocationEnv
from aqp_rl.envs.stock_trading_env import StockTradingEnv
from aqp_rl.evaluator import evaluate_policy
from aqp_rl.runtime import RLRuntime, RLRunResult, runtime_for
from aqp_rl.spec import RLExperimentSpec
from aqp_rl.trainer import train_from_config

# Eager imports so the metaclass registers every component on first
# ``aqp_rl`` import. Each is wrapped to keep optional deps optional.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import actions, observations, rewards, terminations  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import data_pipelines  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import ensemblers, experiments  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import envs  # noqa: F401
# Hybrid agentic-RL Phase 2 + Phase 3: eager-import the new
# advantage estimators + policy backbones so the RLComponent
# metaclass auto-registration fires and `/rl/components/{kind}`
# enumerates them.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import advantage  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import policies  # noqa: F401
# Hybrid agentic-RL Phase 1: eager-import the weight-centric
# portfolio pipeline + RL ↔ Backtest bridge so RLBacktestEnv and
# the WeightCentricPipeline are reachable via build_from_config.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import portfolio  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import bridges  # noqa: F401
# Phase 2 (production-enhancement plan): eager-import the analytical
# baselines so :class:`AlmgrenChrissResidualPolicy` and
# :class:`AvellanedaStoikovResidualPolicy` can ``build_from_config``
# without an explicit ``from aqp_rl.analytical import ...`` in user
# YAML.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_rl import analytical  # noqa: F401
with _contextlib.suppress(Exception):
    from aqp_rl.tagging import apply_tags as _apply_rl_tags

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
