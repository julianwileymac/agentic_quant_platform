"""GRU model — qlib ``GRU``."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("GRUModel")
class GRUModel(BaseTorchModel):
    """Stacked GRU regressor."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        bidirectional: bool = False,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.bidirectional = bool(bidirectional)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _GRU(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, bidir):
                super().__init__()
                self.rnn = nn.GRU(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    bidirectional=bidir,
                    batch_first=True,
                )
                direction = 2 if bidir else 1
                self.head = nn.Linear(hidden * direction, 1)

            def forward(self, x):
                out, _ = self.rnn(x)
                return self.head(out[:, -1, :]).squeeze(-1)

        return _GRU(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.bidirectional,
        )
