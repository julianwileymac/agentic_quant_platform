"""Vanilla DQN agent."""
from __future__ import annotations

from aqp.core.registry import agent
from aqp.rl.agents.q_family.base import BaseQAgent


@agent("QLearningAgent", tags=("rl", "q-learning", "dqn"))
class QLearningAgent(BaseQAgent):
    name = "q"


__all__ = ["QLearningAgent"]
