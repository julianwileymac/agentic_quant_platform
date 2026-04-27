"""ADARNN — Adaptive RNN (qlib ``pytorch_adarnn.py``).

Compact AdaRNN that learns a per-step attention over an LSTM trajectory,
emphasising informative time steps for non-stationary forecasts.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("ADARNNModel")
class ADARNNModel(BaseTorchModel):
    """LSTM trajectory + step-wise attention pooling."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _ADARNN(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.attn = nn.Linear(hidden, 1)
                self.head = nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                weights = torch.softmax(self.attn(out), dim=1)
                pooled = (weights * out).sum(dim=1)
                return self.head(pooled).squeeze(-1)

        return _ADARNN(
            input_size, self.hidden_size, self.num_layers, self.dropout
        )
