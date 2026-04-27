"""HIST model — Hierarchical concept attention (qlib ``pytorch_hist.py``).

A simplified port that captures the key idea: project sequence features
into a "concept space", attend over a learnable concept bank, and use the
attended concept context together with the LSTM hidden state to forecast.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("HISTModel")
class HISTModel(BaseTorchModel):
    """LSTM encoder + attention over a learnable concept bank."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        n_concepts: int = 32,
        concept_dim: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.n_concepts = int(n_concepts)
        self.concept_dim = int(concept_dim) if concept_dim else int(hidden_size)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _HIST(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, n_concepts, concept_dim):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.proj = nn.Linear(hidden, concept_dim)
                self.concepts = nn.Parameter(torch.randn(n_concepts, concept_dim) * 0.05)
                self.head = nn.Sequential(
                    nn.Linear(hidden + concept_dim, hidden),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.Linear(hidden, 1),
                )

            def forward(self, x):
                out, _ = self.lstm(x)
                last = out[:, -1, :]
                q = self.proj(last)
                attn = torch.softmax(q @ self.concepts.t(), dim=-1)
                ctx = attn @ self.concepts
                return self.head(torch.cat([last, ctx], dim=-1)).squeeze(-1)

        return _HIST(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.n_concepts,
            self.concept_dim,
        )
