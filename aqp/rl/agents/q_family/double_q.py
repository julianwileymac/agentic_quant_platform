"""Double DQN — decouple action selection from evaluation."""
from __future__ import annotations

from aqp.core.registry import agent
from aqp.rl.agents.q_family.base import BaseQAgent


@agent("DoubleQAgent", tags=("rl", "q-learning", "double-dqn"))
class DoubleQAgent(BaseQAgent):
    name = "double-q"

    def _q_target(self, torch, rewards, next_states, dones):
        with torch.no_grad():
            next_actions = self.q_net(next_states).argmax(dim=1, keepdim=True)
            next_q = self.target_net(next_states).gather(1, next_actions).squeeze(1)
            return rewards + self.gamma * next_q * (1 - dones)


__all__ = ["DoubleQAgent"]
