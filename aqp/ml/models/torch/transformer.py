"""Transformer encoder model — qlib ``TransformerModel``."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("TransformerModel")
class TransformerModel(BaseTorchModel):
    """Encoder-only transformer over ``(B, step_len, F)`` windows."""

    is_sequence = True

    def __init__(
        self,
        d_model: int = 64,
        n_heads: int = 4,
        num_layers: int = 3,
        dim_feedforward: int = 128,
        dropout: float = 0.1,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.d_model = int(d_model)
        self.n_heads = int(n_heads)
        self.num_layers = int(num_layers)
        self.dim_feedforward = int(dim_feedforward)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _Transformer(nn.Module):
            def __init__(self, in_f, d_model, heads, layers, ff, dropout, step_len):
                super().__init__()
                self.proj = nn.Linear(in_f, d_model)
                self.pos = nn.Parameter(torch.randn(1, step_len, d_model) * 0.02)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=d_model,
                    nhead=heads,
                    dim_feedforward=ff,
                    dropout=dropout,
                    batch_first=True,
                )
                self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=layers)
                self.head = nn.Linear(d_model, 1)

            def forward(self, x):
                h = self.proj(x) + self.pos[:, : x.size(1), :]
                h = self.encoder(h)
                return self.head(h[:, -1, :]).squeeze(-1)

        return _Transformer(
            input_size,
            self.d_model,
            self.n_heads,
            self.num_layers,
            self.dim_feedforward,
            self.dropout,
            self.step_len,
        )
