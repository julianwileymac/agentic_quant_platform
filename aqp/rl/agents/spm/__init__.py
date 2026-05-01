"""SPM (Stock-Prediction-Models) RL agent ports.

Many SPM agent variants overlap with the existing ``q_family`` /
``actor_critic`` / ``evolutionary`` packages. We re-export those with an
``stock_prediction_models`` source tag so the UI taxonomy lists them
under "SPM", and add the genuinely-missing four:

- :class:`DoubleDuelingDQNAgent` — Double + Dueling Q-network.
- :class:`PolicyGradientAgent` — REINFORCE.
- :class:`A3CAgent` — single-process A2C variant (true async A3C left to SB3).
- :class:`ActorCriticExperienceReplayAgent` — actor-critic with off-policy replay.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp.core.registry import tag_class

# Tag the existing classes so they surface under ``source:stock_prediction_models``.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.q_family import (
        DoubleQAgent as _DoubleQAgent,
        DuelQAgent as _DuelQAgent,
        QLearningAgent as _QLearningAgent,
        RecurrentQAgent as _RecurrentQAgent,
    )

    for _cls in (_QLearningAgent, _DoubleQAgent, _DuelQAgent, _RecurrentQAgent):
        tag_class(_cls, "source:stock_prediction_models")

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.actor_critic import (
        ActorCriticAgent as _ActorCriticAgent,
        ActorCriticDuelAgent as _ActorCriticDuelAgent,
        ActorCriticRecurrentAgent as _ActorCriticRecurrentAgent,
    )

    for _cls in (_ActorCriticAgent, _ActorCriticDuelAgent, _ActorCriticRecurrentAgent):
        tag_class(_cls, "source:stock_prediction_models")

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.evolutionary import EvolutionStrategyAgent as _EvolutionStrategyAgent

    tag_class(_EvolutionStrategyAgent, "source:stock_prediction_models")

# New SPM-specific agents.
from aqp.rl.agents.spm.agents import (  # noqa: F401  (registers via @register)
    A3CAgent,
    ActorCriticExperienceReplayAgent,
    DoubleDuelingDQNAgent,
    PolicyGradientAgent,
)


__all__ = [
    "A3CAgent",
    "ActorCriticExperienceReplayAgent",
    "DoubleDuelingDQNAgent",
    "PolicyGradientAgent",
]
