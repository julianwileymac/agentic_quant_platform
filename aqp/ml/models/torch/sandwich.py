"""Sandwich — qlib ``pytorch_sandwich.py``.

The Sandwich model alternates CNN and RNN blocks (CNN → RNN → CNN → RNN).
Compact two-block variant here for our framework.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("SandwichModel")
class SandwichModel(BaseTorchModel):
    """Conv1d → GRU → Conv1d → GRU → linear head."""

    is_sequence = True

    def __init__(
        self,
        cnn_channels: int = 32,
        hidden_size: int = 64,
        kernel_size: int = 3,
        dropout: float = 0.2,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.cnn_channels = int(cnn_channels)
        self.hidden_size = int(hidden_size)
        self.kernel_size = int(kernel_size)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _Sandwich(nn.Module):
            def __init__(self, in_f, channels, hidden, kernel, dropout):
                super().__init__()
                self.cnn1 = nn.Conv1d(in_f, channels, kernel, padding=kernel // 2)
                self.gru1 = nn.GRU(channels, hidden, batch_first=True)
                self.cnn2 = nn.Conv1d(hidden, channels, kernel, padding=kernel // 2)
                self.gru2 = nn.GRU(channels, hidden, batch_first=True)
                self.dropout = nn.Dropout(dropout)
                self.head = nn.Linear(hidden, 1)

            def forward(self, x):
                x = x.transpose(1, 2)
                x = torch.relu(self.cnn1(x)).transpose(1, 2)
                x, _ = self.gru1(x)
                x = self.dropout(x)
                x = x.transpose(1, 2)
                x = torch.relu(self.cnn2(x)).transpose(1, 2)
                x, _ = self.gru2(x)
                return self.head(x[:, -1, :]).squeeze(-1)

        return _Sandwich(
            input_size,
            self.cnn_channels,
            self.hidden_size,
            self.kernel_size,
            self.dropout,
        )
