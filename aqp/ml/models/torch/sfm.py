"""SFM — State Frequency Memory (qlib ``pytorch_sfm.py``).

The original SFM cell decomposes the LSTM hidden state into multiple
frequency components. This port keeps the spirit by running K parallel
LSTM tracks at different sampling rates (subsampled inputs) and pooling
the final hidden states into a single forecast.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("SFMModel")
class SFMModel(BaseTorchModel):
    """Multi-frequency parallel-LSTM forecaster."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 32,
        num_layers: int = 1,
        dropout: float = 0.2,
        step_len: int = 20,
        freq_count: int = 4,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.freq_count = max(1, int(freq_count))

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _SFM(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, freq_count):
                super().__init__()
                self.tracks = nn.ModuleList(
                    [
                        nn.LSTM(
                            in_f,
                            hidden,
                            num_layers=layers,
                            dropout=dropout if layers > 1 else 0.0,
                            batch_first=True,
                        )
                        for _ in range(freq_count)
                    ]
                )
                self.freq_count = freq_count
                self.head = nn.Linear(hidden * freq_count, 1)

            def forward(self, x):
                outs = []
                for k, lstm in enumerate(self.tracks):
                    stride = max(1, k + 1)
                    sub = x[:, ::stride, :]
                    out, _ = lstm(sub)
                    outs.append(out[:, -1, :])
                pooled = torch.cat(outs, dim=-1)
                return self.head(pooled).squeeze(-1)

        return _SFM(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.freq_count,
        )
