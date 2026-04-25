"""Explicit bidirectional RNN variants.

``LSTMModel`` / ``GRUModel`` accept a ``bidirectional`` flag, but the
Strategy Browser surfaces classes one-to-one, so we register these as
their own kind for visibility.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import model
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


def _build_bidir(torch, rnn_cls, input_size: int, hidden: int, layers: int, dropout: float):
    nn = torch.nn

    class _BiRNN(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.rnn = rnn_cls(
                input_size,
                hidden,
                num_layers=layers,
                dropout=dropout if layers > 1 else 0.0,
                bidirectional=True,
                batch_first=True,
            )
            self.head = nn.Linear(hidden * 2, 1)

        def forward(self, x):
            out, _ = self.rnn(x)
            return self.head(out[:, -1, :]).squeeze(-1)

    return _BiRNN()


@model("BidirectionalLSTMModel", tags=("torch", "rnn", "lstm", "bidirectional"))
class BidirectionalLSTMModel(BaseTorchModel):
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
        return _build_bidir(
            torch, torch.nn.LSTM, input_size, self.hidden_size, self.num_layers, self.dropout
        )


@model("BidirectionalGRUModel", tags=("torch", "rnn", "gru", "bidirectional"))
class BidirectionalGRUModel(BaseTorchModel):
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
        return _build_bidir(
            torch, torch.nn.GRU, input_size, self.hidden_size, self.num_layers, self.dropout
        )


__all__ = ["BidirectionalGRUModel", "BidirectionalLSTMModel"]
