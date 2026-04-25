"""Recurrent DQN — LSTM encoder over an observation window."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import agent
from aqp.rl.agents.q_family.base import BaseQAgent


@agent("RecurrentQAgent", tags=("rl", "q-learning", "recurrent"))
class RecurrentQAgent(BaseQAgent):
    name = "recurrent-q"
    recurrent = True

    def _build_network(self, torch: Any) -> Any:
        nn = torch.nn
        hidden = self.hidden_size
        n_actions = self.n_actions
        state_dim = self.state_dim

        class _LSTM_Q(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.rnn = nn.LSTM(state_dim, hidden, batch_first=True)
                self.head = nn.Linear(hidden, n_actions)

            def forward(self, x):
                if x.dim() == 2:
                    x = x.unsqueeze(1)  # (B, 1, F)
                out, _ = self.rnn(x)
                return self.head(out[:, -1, :])

        return _LSTM_Q().to(self.device)


__all__ = ["RecurrentQAgent"]
