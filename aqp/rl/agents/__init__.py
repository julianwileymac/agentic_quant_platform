"""RL agent adapters.

Tiers:

- :class:`SB3Adapter` — Stable-Baselines3 + sb3-contrib (PPO/A2C/DDPG/TD3/SAC/DQN/RecurrentPPO/TRPO/QRDQN/MaskablePPO).
- :class:`ElegantRLAdapter` — `ElegantRL` (FinRL parity for the second supported backend).
- :class:`RayRLlibAdapter` — Ray RLlib (scalable distributed training).
- :class:`CleanRLAdapter` — single-file PPO reference implementation.
- :class:`LLMHybridAgent` — FinRobot-style LLM advisor blended with any RL backbone.
- ``classical/`` — rule-based heuristic agents (Turtle, Moving-Average,
  Signal-Rolling, ABCD).
- ``q_family/`` — DQN variants (Vanilla, Double, Duel, Recurrent, Curiosity).
- ``actor_critic/`` — on-policy A2C-flavoured agents with optional duelling / recurrent heads.
- ``evolutionary/`` — gradient-free optimisers (ES, NEAT, Novelty).

Heavy imports are suppressed so ``from aqp.rl.agents import SB3Adapter``
remains cheap when third-party deps are missing.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp.rl.agents.sb3_adapter import SB3Adapter, list_supported_algorithms

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.elegantrl_adapter import ElegantRLAdapter  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.rllib_adapter import RayRLlibAdapter  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.cleanrl_adapter import CleanRLAdapter  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.llm_hybrid import LLMHybridAgent  # noqa: F401

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

# SPM agent ports (re-tagging existing classes + 4 net-new agents).
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.rl.agents.spm import (  # noqa: F401
        A3CAgent,
        ActorCriticExperienceReplayAgent,
        DoubleDuelingDQNAgent,
        PolicyGradientAgent,
    )

__all__ = ["SB3Adapter", "list_supported_algorithms"]
