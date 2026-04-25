"""Recurrent Actor-Critic variant."""
from __future__ import annotations

from aqp.core.registry import agent
from aqp.rl.agents.actor_critic.actor_critic import ActorCriticAgent


@agent("ActorCriticRecurrentAgent", tags=("rl", "actor-critic", "recurrent"))
class ActorCriticRecurrentAgent(ActorCriticAgent):
    recurrent = True
    name = "ac-recurrent"


__all__ = ["ActorCriticRecurrentAgent"]
