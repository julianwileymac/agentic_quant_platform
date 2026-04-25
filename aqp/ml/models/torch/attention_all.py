"""Vanilla "Attention is all you need" transformer encoder forecaster.

A slightly different surface than the existing
:class:`aqp.ml.models.torch.transformer.TransformerModel`: no positional
encoding via module_list but the canonical sinusoidal PE, classical
multi-head self-attention with ``d_model = hidden_size``. Mirrors the
Stock-Prediction-Models ``attention-is-all-you-need.ipynb`` reference.
"""
from __future__ import annotations

import math
from typing import Any

from aqp.core.registry import model
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@model("AttentionAllModel", tags=("torch", "transformer", "attention-all"))
class AttentionAllModel(BaseTorchModel):
    is_sequence = True

    def __init__(
        self,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 128,
        dropout: float = 0.1,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.d_model = int(d_model)
        self.nhead = int(nhead)
        self.num_layers = int(num_layers)
        self.dim_feedforward = int(dim_feedforward)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        d_model = self.d_model
        nhead = self.nhead
        num_layers = self.num_layers
        dim_feedforward = self.dim_feedforward
        dropout = self.dropout

        class _PositionalEncoding(nn.Module):
            def __init__(self, d_model: int, max_len: int = 5000):
                super().__init__()
                pe = torch.zeros(max_len, d_model)
                position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
                div_term = torch.exp(
                    torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
                )
                pe[:, 0::2] = torch.sin(position * div_term)
                pe[:, 1::2] = torch.cos(position * div_term)
                self.register_buffer("pe", pe.unsqueeze(0))

            def forward(self, x):
                return x + self.pe[:, : x.size(1)]

        class _AttentionAll(nn.Module):
            def __init__(self):
                super().__init__()
                self.embed = nn.Linear(input_size, d_model)
                self.pe = _PositionalEncoding(d_model)
                self.encoder = nn.TransformerEncoder(
                    nn.TransformerEncoderLayer(
                        d_model=d_model,
                        nhead=nhead,
                        dim_feedforward=dim_feedforward,
                        dropout=dropout,
                        batch_first=True,
                    ),
                    num_layers=num_layers,
                )
                self.head = nn.Linear(d_model, 1)

            def forward(self, x):
                h = self.embed(x)
                h = self.pe(h)
                h = self.encoder(h)
                return self.head(h[:, -1, :]).squeeze(-1)

        return _AttentionAll()


__all__ = ["AttentionAllModel"]
