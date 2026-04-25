"""Localformer — Transformer with local attention bias (qlib ``Localformer``)."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("LocalformerModel")
class LocalformerModel(BaseTorchModel):
    """Lightweight local-attention encoder.

    The attention mask restricts each position to a sliding window of
    ``local_window`` neighbours, biasing the model toward local patterns.
    """

    is_sequence = True

    def __init__(
        self,
        d_model: int = 64,
        n_heads: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 128,
        dropout: float = 0.1,
        local_window: int = 8,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.d_model = int(d_model)
        self.n_heads = int(n_heads)
        self.num_layers = int(num_layers)
        self.dim_feedforward = int(dim_feedforward)
        self.dropout = float(dropout)
        self.local_window = int(local_window)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        def _local_mask(seq_len: int, window: int) -> torch.Tensor:
            mask = torch.ones(seq_len, seq_len) * float("-inf")
            for i in range(seq_len):
                lo = max(0, i - window)
                hi = min(seq_len, i + window + 1)
                mask[i, lo:hi] = 0.0
            return mask

        class _Localformer(nn.Module):
            def __init__(self, in_f, d_model, heads, layers, ff, dropout, win, step_len):
                super().__init__()
                self.proj = nn.Linear(in_f, d_model)
                self.pos = nn.Parameter(torch.randn(1, step_len, d_model) * 0.02)
                layer = nn.TransformerEncoderLayer(
                    d_model=d_model,
                    nhead=heads,
                    dim_feedforward=ff,
                    dropout=dropout,
                    batch_first=True,
                )
                self.encoder = nn.TransformerEncoder(layer, num_layers=layers)
                self.register_buffer("_mask", _local_mask(step_len, win))
                self.head = nn.Linear(d_model, 1)

            def forward(self, x):
                h = self.proj(x) + self.pos[:, : x.size(1), :]
                mask = self._mask[: x.size(1), : x.size(1)]
                h = self.encoder(h, mask=mask)
                return self.head(h[:, -1, :]).squeeze(-1)

        return _Localformer(
            input_size,
            self.d_model,
            self.n_heads,
            self.num_layers,
            self.dim_feedforward,
            self.dropout,
            self.local_window,
            self.step_len,
        )
