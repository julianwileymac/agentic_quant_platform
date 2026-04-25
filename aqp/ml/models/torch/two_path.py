"""Two-path recurrent encoders (Stock-Prediction-Models).

The idea: run two parallel RNN encoders with different receptive fields
(full window vs. last-``k`` steps) and concatenate their final hidden
states before the regression head. Empirically improves generalisation
on short windows where a single RNN under-fits the short-term dynamics.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import model
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


def _build_two_path(torch, rnn_cls, input_size: int, hidden: int, layers: int, dropout: float, tail_k: int):
    nn = torch.nn

    class _TwoPath(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.full = rnn_cls(
                input_size, hidden, num_layers=layers, dropout=dropout if layers > 1 else 0.0, batch_first=True
            )
            self.tail = rnn_cls(
                input_size, hidden, num_layers=layers, dropout=dropout if layers > 1 else 0.0, batch_first=True
            )
            self.head = nn.Linear(hidden * 2, 1)
            self.tail_k = tail_k

        def forward(self, x):  # (B, T, F)
            full_out, _ = self.full(x)
            tail_out, _ = self.tail(x[:, -self.tail_k :, :])
            concat = torch.cat([full_out[:, -1, :], tail_out[:, -1, :]], dim=-1)
            return self.head(concat).squeeze(-1)

    return _TwoPath()


@model("TwoPathLSTMModel", tags=("torch", "rnn", "lstm", "two-path"))
class TwoPathLSTMModel(BaseTorchModel):
    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        tail_k: int = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.tail_k = int(min(tail_k, step_len))

    def build_module(self, input_size: int):
        torch = _import_torch()
        return _build_two_path(
            torch, torch.nn.LSTM, input_size, self.hidden_size, self.num_layers, self.dropout, self.tail_k
        )


@model("TwoPathGRUModel", tags=("torch", "rnn", "gru", "two-path"))
class TwoPathGRUModel(BaseTorchModel):
    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        tail_k: int = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.tail_k = int(min(tail_k, step_len))

    def build_module(self, input_size: int):
        torch = _import_torch()
        return _build_two_path(
            torch, torch.nn.GRU, input_size, self.hidden_size, self.num_layers, self.dropout, self.tail_k
        )


__all__ = ["TwoPathGRUModel", "TwoPathLSTMModel"]
