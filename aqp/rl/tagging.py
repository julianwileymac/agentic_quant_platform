"""Apply paradigm + algo-family tags to existing RL agents.

We don't touch the individual agent files — instead we walk the
registry once (after :mod:`aqp.rl.agents` has loaded) and call
:func:`aqp.core.registry.tag_class` to attach tags. The Strategy
Browser, Taxonomy Explorer, and ``list_by_tag`` all pick the tags up
without any class-level decorator changes.

Importing this module is a side-effect — call ``apply_tags()`` once.
"""
from __future__ import annotations

import logging
from typing import Iterable

from aqp.core.registry import tag_class

logger = logging.getLogger(__name__)


_PARADIGM_TAGS: dict[str, dict[str, Iterable[str]]] = {
    "aqp.rl.agents.classical": {
        "moving_average.MovingAverageAgent": ("paradigm:rl_classical", "algo_family:moving_average"),
        "turtle.TurtleAgent": ("paradigm:rl_classical", "algo_family:trend"),
        "abcd.ABCDStrategyAgent": ("paradigm:rl_classical", "algo_family:pattern"),
        "signal_rolling.SignalRollingAgent": ("paradigm:rl_classical", "algo_family:signal_rolling"),
    },
    "aqp.rl.agents.q_family": {
        "q_learning.QLearningAgent": ("paradigm:reinforcement", "algo_family:q_learning"),
        "double_q.DoubleQAgent": ("paradigm:reinforcement", "algo_family:double_q"),
        "duel_q.DuelQAgent": ("paradigm:reinforcement", "algo_family:dueling_q"),
        "recurrent_q.RecurrentQAgent": ("paradigm:reinforcement", "algo_family:recurrent_q"),
        "curiosity_q.CuriosityQAgent": ("paradigm:reinforcement", "algo_family:curiosity_q"),
    },
    "aqp.rl.agents.actor_critic": {
        "actor_critic.ActorCriticAgent": ("paradigm:reinforcement", "algo_family:actor_critic"),
        "actor_critic_duel.ActorCriticDuelAgent": ("paradigm:reinforcement", "algo_family:actor_critic_duel"),
        "actor_critic_recurrent.ActorCriticRecurrentAgent": (
            "paradigm:reinforcement",
            "algo_family:actor_critic_recurrent",
        ),
    },
    "aqp.rl.agents.evolutionary": {
        "es.EvolutionStrategyAgent": ("paradigm:evolutionary", "algo_family:es"),
        "neuro.NeuroEvolutionAgent": ("paradigm:evolutionary", "algo_family:neat"),
        "novelty.NeuroEvolutionNoveltyAgent": ("paradigm:evolutionary", "algo_family:novelty"),
    },
    "aqp.rl.envs": {
        "stock_trading_env.StockTradingEnv": ("kind:env", "domain:single_stock"),
        "stock_trading_discrete.StockTradingDiscreteEnv": ("kind:env", "domain:single_stock_discrete"),
        "portfolio_env.PortfolioAllocationEnv": ("kind:env", "domain:portfolio"),
    },
    "aqp.ml.applications.forecaster": {
        "auto_arima.AutoArimaForecaster": ("paradigm:supervised", "algo_family:arima", "ts:arima"),
        "prophet_adapter.ProphetForecaster": ("paradigm:supervised", "algo_family:prophet", "ts:prophet"),
        "sktime_adapter.SktimeForecaster": ("paradigm:supervised", "algo_family:sktime", "ts:sktime"),
        "statsmodels_adapter.StatsmodelsForecaster": (
            "paradigm:supervised",
            "algo_family:statsmodels",
            "ts:state_space",
        ),
    },
}


def _resolve(qualname: str) -> type | None:
    parts = qualname.split(".")
    module_path = ".".join(parts[:-1])
    cls_name = parts[-1]
    try:
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name, None)
    except Exception:
        return None


def apply_tags() -> int:
    """Walk the curated mapping and tag each class. Returns count of classes tagged."""
    tagged = 0
    for base_module, members in _PARADIGM_TAGS.items():
        for rel_name, tags in members.items():
            full = f"{base_module}.{rel_name}"
            cls = _resolve(full)
            if cls is None:
                logger.debug("rl tagging: cannot resolve %s", full)
                continue
            tag_class(cls, *tags)
            tagged += 1
    logger.debug("rl tagging: tagged %d classes", tagged)
    return tagged


__all__ = ["apply_tags"]
