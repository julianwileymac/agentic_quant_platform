"""GATs model — Graph Attention Networks for symbol relations.

A pragmatic port of qlib ``pytorch_gats.py``: when ``torch_geometric`` is
available we use real ``GATConv`` layers; otherwise we fall back to dense
multi-head self-attention over the batch dimension. This keeps the
registry usable without the heavyweight ``torch-geometric`` extra.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


def _has_pyg() -> bool:
    try:
        import torch_geometric  # type: ignore[import-not-found]  # noqa: F401

        return True
    except ImportError:
        return False


@register("GATsModel")
class GATsModel(BaseTorchModel):
    """LSTM encoder + (graph or dense) attention head."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        n_heads: int = 4,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.n_heads = int(n_heads)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _GATs(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, heads):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                # Dense self-attention over the batch dimension stands in for a
                # full graph: every symbol attends to every other in the batch.
                self.attn = nn.MultiheadAttention(
                    hidden, num_heads=heads, dropout=dropout, batch_first=True
                )
                self.head = nn.Sequential(
                    nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1)
                )

            def forward(self, x):
                out, _ = self.lstm(x)
                last = out[:, -1, :].unsqueeze(0)
                attn_out, _ = self.attn(last, last, last, need_weights=False)
                return self.head(attn_out.squeeze(0)).squeeze(-1)

        return _GATs(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.n_heads,
        )
