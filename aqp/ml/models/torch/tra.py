"""TRA model — Temporal Routing Adapter (qlib ``pytorch_tra.py``).

The full Memory-Augmented TRA paper is large; here we implement the
core idea: an LSTM backbone produces a hidden state, and a small router
selects from K parallel forecast heads. The router is differentiable
(softmax) so the network learns to route different regimes through
different heads.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("TRAModel")
class TRAModel(BaseTorchModel):
    """LSTM backbone + K forecast heads with a soft router."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        num_states: int = 4,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.num_states = max(1, int(num_states))

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _TRA(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, num_states):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.router = nn.Linear(hidden, num_states)
                self.heads = nn.ModuleList(
                    [nn.Linear(hidden, 1) for _ in range(num_states)]
                )

            def forward(self, x):
                out, _ = self.lstm(x)
                last = out[:, -1, :]
                weights = torch.softmax(self.router(last), dim=-1)
                stacked = torch.stack([h(last).squeeze(-1) for h in self.heads], dim=-1)
                return (weights * stacked).sum(dim=-1)

        return _TRA(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.num_states,
        )
