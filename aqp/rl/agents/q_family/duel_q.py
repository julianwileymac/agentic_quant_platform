"""Dueling DQN — split the Q-head into value + advantage streams."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import agent
from aqp.rl.agents.q_family.base import BaseQAgent


@agent("DuelQAgent", tags=("rl", "q-learning", "dueling-dqn"))
class DuelQAgent(BaseQAgent):
    name = "duel-q"

    def _build_network(self, torch: Any) -> Any:
        nn = torch.nn
        hidden = self.hidden_size
        n_actions = self.n_actions
        state_dim = self.state_dim

        class _Duel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.feature = nn.Sequential(
                    nn.Linear(state_dim, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, hidden),
                    nn.ReLU(),
                )
                self.value = nn.Linear(hidden, 1)
                self.advantage = nn.Linear(hidden, n_actions)

            def forward(self, x):
                h = self.feature(x)
                v = self.value(h)
                a = self.advantage(h)
                return v + a - a.mean(dim=-1, keepdim=True)

        return _Duel().to(self.device)


__all__ = ["DuelQAgent"]
