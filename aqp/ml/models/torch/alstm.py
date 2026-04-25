"""ALSTM — attention-augmented LSTM (qlib ``ALSTM``)."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("ALSTMModel")
class ALSTMModel(BaseTorchModel):
    """LSTM + scaled dot-product attention head."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        attention_heads: int = 4,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.attention_heads = int(attention_heads)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _ALSTM(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, heads):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.attn = nn.MultiheadAttention(hidden, num_heads=heads, batch_first=True)
                self.head = nn.Sequential(nn.Linear(hidden, hidden // 2), nn.ReLU(), nn.Linear(hidden // 2, 1))

            def forward(self, x):
                out, _ = self.lstm(x)
                attn_out, _ = self.attn(out, out, out, need_weights=False)
                pooled = attn_out.mean(dim=1)
                return self.head(pooled).squeeze(-1)

        return _ALSTM(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.attention_heads,
        )
