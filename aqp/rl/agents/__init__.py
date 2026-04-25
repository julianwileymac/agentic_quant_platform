"""RL agent adapters.

Three tiers live here:

- :class:`SB3Adapter` — thin wrapper over Stable-Baselines3 (PPO/A2C/DDPG/TD3/SAC).
- ``classical/`` — rule-based heuristic agents (Turtle, Moving-Average,
  Signal-Rolling, ABCD). No gradients, no replay.
- ``q_family/`` — DQN variants (Vanilla, Double, Duel, Recurrent, Curiosity).
- ``actor_critic/`` — on-policy A2C-flavoured agents with optional
  duelling / recurrent heads.
- ``evolutionary/`` — gradient-free optimisers (Evolution Strategies,
  Neuro-Evolution, Novelty Search).

Heavy imports are suppressed so ``from aqp.rl.agents import SB3Adapter``
remains cheap when torch is absent.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp.rl.agents.sb3_adapter import SB3Adapter

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.classical import (  # noqa: F401
        ABCDStrategyAgent,
        BaseClassicalAgent,
        MovingAverageAgent,
        SignalRollingAgent,
        TurtleAgent,
    )
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.q_family import (  # noqa: F401
        BaseQAgent,
        CuriosityQAgent,
        DoubleQAgent,
        DuelQAgent,
        QLearningAgent,
        RecurrentQAgent,
    )
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.actor_critic import (  # noqa: F401
        ActorCriticAgent,
        ActorCriticDuelAgent,
        ActorCriticRecurrentAgent,
    )
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.evolutionary import (  # noqa: F401
        EvolutionStrategyAgent,
        NeuroEvolutionAgent,
        NeuroEvolutionNoveltyAgent,
    )

__all__ = ["SB3Adapter"]
