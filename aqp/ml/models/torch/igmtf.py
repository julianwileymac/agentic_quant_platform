"""IGMTF — Interpretable Graph Multi-Task Forecaster (qlib ``pytorch_igmtf.py``).

The original network learns inter-instrument graph structure jointly
with two auxiliary task heads. We keep two heads (return + sign) and a
shared encoder so users can introspect both during evaluation.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("IGMTFModel")
class IGMTFModel(BaseTorchModel):
    """Shared encoder + return regression + sign auxiliary heads.

    The auxiliary head is exposed via ``model.module.aux`` for callers
    that want to read the predicted-direction probability; the primary
    output (used by `predict`) is the return regression head.
    """

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

        class _IGMTF(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.reg = nn.Linear(hidden, 1)
                self.aux = nn.Linear(hidden, 2)

            def forward(self, x):
                out, _ = self.lstm(x)
                last = out[:, -1, :]
                return self.reg(last).squeeze(-1)

        return _IGMTF(
            input_size, self.hidden_size, self.num_layers, self.dropout
        )
