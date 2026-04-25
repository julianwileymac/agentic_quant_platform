"""Curiosity-driven DQN — ICM-style intrinsic reward.

Adds a forward-model head that predicts the next state from
``(state, action)`` and uses the prediction error as an intrinsic reward
that is added to the environment reward before storage in the replay
buffer.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from aqp.core.registry import agent
from aqp.rl.agents.q_family.base import BaseQAgent, _import_torch


@agent("CuriosityQAgent", tags=("rl", "q-learning", "curiosity", "icm"))
class CuriosityQAgent(BaseQAgent):
    name = "curiosity-q"

    def __init__(self, *args: Any, curiosity_weight: float = 0.01, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.curiosity_weight = float(curiosity_weight)
        torch = _import_torch()
        nn = torch.nn

        class _Forward(nn.Module):
            def __init__(self, state_dim: int, n_actions: int, hidden: int) -> None:
                super().__init__()
                self.action_embed = nn.Embedding(n_actions, hidden)
                self.model = nn.Sequential(
                    nn.Linear(state_dim + hidden, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, state_dim),
                )

            def forward(self, state, action):
                emb = self.action_embed(action)
                return self.model(torch.cat([state, emb], dim=-1))

        self.forward_model = _Forward(self.state_dim, self.n_actions, self.hidden_size).to(self.device)
        self.forward_optim = torch.optim.Adam(self.forward_model.parameters(), lr=self.lr)

    def _intrinsic(self, state, action, next_state) -> float:
        torch = _import_torch()
        state_t = torch.tensor(np.asarray(state, dtype=np.float32)).unsqueeze(0).to(self.device)
        next_t = torch.tensor(np.asarray(next_state, dtype=np.float32)).unsqueeze(0).to(self.device)
        action_t = torch.tensor([int(action)], dtype=torch.long).to(self.device)
        pred = self.forward_model(state_t, action_t)
        error = torch.nn.functional.mse_loss(pred, next_t)
        self.forward_optim.zero_grad()
        error.backward()
        self.forward_optim.step()
        return float(error.detach().item())

    def remember(self, *, state, action, reward, next_state, done) -> None:
        intrinsic = self._intrinsic(state, action, next_state)
        shaped = reward + self.curiosity_weight * intrinsic
        super().remember(state=state, action=action, reward=shaped, next_state=next_state, done=done)


__all__ = ["CuriosityQAgent"]
