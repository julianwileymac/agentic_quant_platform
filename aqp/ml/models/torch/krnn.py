"""KRNN — Kernelized RNN (qlib ``pytorch_krnn.py``).

KRNN runs a 1-D convolutional "kernel" over the time axis to produce
local features which are then consumed by an RNN. Reproduced as Conv1d
+ GRU + linear head.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("KRNNModel")
class KRNNModel(BaseTorchModel):
    """Conv1d local kernel + GRU + linear head."""

    is_sequence = True

    def __init__(
        self,
        kernel_size: int = 3,
        cnn_channels: int = 32,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.2,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.kernel_size = int(kernel_size)
        self.cnn_channels = int(cnn_channels)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _KRNN(nn.Module):
            def __init__(self, in_f, kernel, channels, hidden, layers, dropout):
                super().__init__()
                self.cnn = nn.Conv1d(
                    in_f,
                    channels,
                    kernel_size=kernel,
                    padding=kernel // 2,
                )
                self.act = nn.ReLU()
                self.rnn = nn.GRU(
                    channels,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.head = nn.Linear(hidden, 1)

            def forward(self, x):
                # x: (B, T, F) → (B, F, T) for Conv1d
                x = x.transpose(1, 2)
                x = self.act(self.cnn(x)).transpose(1, 2)
                out, _ = self.rnn(x)
                return self.head(out[:, -1, :]).squeeze(-1)

        return _KRNN(
            input_size,
            self.kernel_size,
            self.cnn_channels,
            self.hidden_size,
            self.num_layers,
            self.dropout,
        )
