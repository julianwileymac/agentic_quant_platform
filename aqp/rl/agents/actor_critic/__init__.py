"""Actor-Critic family — classical A2C variants (non-SB3)."""
from __future__ import annotations

from aqp.rl.agents.actor_critic.actor_critic import ActorCriticAgent
from aqp.rl.agents.actor_critic.actor_critic_duel import ActorCriticDuelAgent
from aqp.rl.agents.actor_critic.actor_critic_recurrent import ActorCriticRecurrentAgent

__all__ = [
    "ActorCriticAgent",
    "ActorCriticDuelAgent",
    "ActorCriticRecurrentAgent",
]
