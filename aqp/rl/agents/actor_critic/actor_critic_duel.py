"""Dueling Actor-Critic variant."""
from __future__ import annotations

from aqp.core.registry import agent
from aqp.rl.agents.actor_critic.actor_critic import ActorCriticAgent


@agent("ActorCriticDuelAgent", tags=("rl", "actor-critic", "dueling"))
class ActorCriticDuelAgent(ActorCriticAgent):
    duel = True
    name = "ac-duel"


__all__ = ["ActorCriticDuelAgent"]
