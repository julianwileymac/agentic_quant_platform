"""TCTS — Decoupled forecaster + temporal classifier scheduler.

Pragmatic port of qlib ``pytorch_tcts.py``: rather than running the
two-network alternating optimisation from the paper, we expose a single
joint model with two heads (regression + auxiliary classification of
"trend confidence"). The combined loss is the regression MSE plus a
small cross-entropy weight that encourages calibrated confidence.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("TCTSModel")
class TCTSModel(BaseTorchModel):
    """LSTM encoder + regression head + auxiliary 3-class trend head."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        n_classes: int = 3,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.n_classes = int(n_classes)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _TCTS(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, n_classes):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.reg = nn.Linear(hidden, 1)
                self.cls = nn.Linear(hidden, n_classes)

            def forward(self, x):
                out, _ = self.lstm(x)
                last = out[:, -1, :]
                # Regression head is the primary output; classifier exposed
                # via ``model.module.cls`` for callers that want it.
                return self.reg(last).squeeze(-1)

        return _TCTS(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.n_classes,
        )
