"""``TransformerBackbone`` — multi-head self-attention encoder for RL policies.

Lightweight, drop-in Transformer encoder tailored for the financial-
time-series scale (typical sequence length 30-100, 8-32 features).
Uses ``torch.nn.TransformerEncoder`` so the parameter count + memory
profile stay well within the budget of a real-time inference path.

The richer Transformer variants used in offline ML forecasting
(``aqp/ml/models/torch/transformer.py``, the HuggingFace
PatchTST/Informer wrappers) are intentionally NOT inherited from
here — those have forecasting heads + position-aware decoders that
are wasteful when all we want is a fixed-dim feature vector for the
policy network. They remain available for separate alpha-research
flows.
"""
from __future__ import annotations

import math
from typing import Any, ClassVar

import numpy as np

from aqp.rl.policies.backbones.base import TimeSeriesEncoder, reshape_obs_to_sequence

try:
    import torch
    from torch import nn

    _TORCH_AVAILABLE = True
except Exception:
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False


class _SinusoidalPositionalEncoding:
    """Lazy sinusoidal positional encoding (computed once per shape)."""

    _cache: dict[tuple[int, int], "torch.Tensor"] = {}

    @classmethod
    def get(cls, seq_len: int, d_model: int) -> "torch.Tensor":
        if not _TORCH_AVAILABLE:
            raise ImportError("torch required for positional encoding")
        key = (int(seq_len), int(d_model))
        if key in cls._cache:
            return cls._cache[key]
        pe = torch.zeros(seq_len, d_model)
        position = torch.arange(0, seq_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        cls._cache[key] = pe.unsqueeze(0)
        return cls._cache[key]


class TransformerBackbone(TimeSeriesEncoder):
    """Self-attention encoder over the most-recent L bars of observation.

    Parameters
    ----------
    input_features:
        Per-bar feature dimensionality (number of channels). The
        env's ``LookbackStackBuilder`` configures this when the
        observation contains per-asset OHLCV + indicators stacked
        across the universe.
    sequence_length:
        Number of historical bars in the sliding window. Defaults to
        30 (one trading-month) for daily envs; bump to 60-120 for
        intraday envs.
    output_dim:
        Final feature vector dimension consumed by the policy head.
        Defaults to ``128`` to keep parameter count modest.
    n_heads, n_layers, d_ff, dropout:
        Standard Transformer hyperparameters. Defaults are tuned for
        a ~50K-parameter encoder that trains well on a single GPU.
    """

    rl_alias: ClassVar[str] = "TransformerBackbone"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "transformer"
    rl_tags: ClassVar[tuple[str, ...]] = ("transformer", "attention", "sequence")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int = 30,
        output_dim: int = 128,
        n_heads: int = 4,
        n_layers: int = 2,
        d_ff: int = 256,
        dropout: float = 0.1,
        d_model: int | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        if not _TORCH_AVAILABLE:
            raise ImportError("TransformerBackbone requires torch")
        self.d_model = int(d_model or output_dim)
        if self.d_model % n_heads != 0:
            # Round up to the nearest multiple of n_heads so MHA works.
            self.d_model = int(math.ceil(self.d_model / n_heads) * n_heads)
        self.n_heads = int(n_heads)
        self.n_layers = int(n_layers)
        self.d_ff = int(d_ff)
        self.dropout = float(dropout)

        self._module = self._build_module()

    def _build_module(self) -> "nn.Module":
        d_model = self.d_model
        input_proj = nn.Linear(self.input_features, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=self.n_heads,
            dim_feedforward=self.d_ff,
            dropout=self.dropout,
            batch_first=True,
        )
        encoder = nn.TransformerEncoder(encoder_layer, num_layers=self.n_layers)
        out_proj = nn.Linear(d_model, self.output_dim)

        backbone = nn.Module()
        backbone.input_proj = input_proj
        backbone.encoder = encoder
        backbone.out_proj = out_proj
        return backbone

    def forward(self, x: Any) -> "torch.Tensor":
        if not _TORCH_AVAILABLE:
            raise ImportError("torch required at inference time")
        if isinstance(x, np.ndarray):
            x = reshape_obs_to_sequence(
                x, sequence_length=self.sequence_length, input_features=self.input_features
            )
            x = torch.from_numpy(x.astype(np.float32))
        elif isinstance(x, torch.Tensor) and x.dim() == 2:
            # Auto-reshape (B, D) -> (B, L, F).
            arr = x.detach().cpu().numpy()
            arr = reshape_obs_to_sequence(
                arr,
                sequence_length=self.sequence_length,
                input_features=self.input_features,
            )
            x = torch.from_numpy(arr.astype(np.float32)).to(x.device)
        elif isinstance(x, torch.Tensor) and x.dim() != 3:
            raise ValueError(
                f"TransformerBackbone expected (B,L,F) or (B,D) tensor, got shape {tuple(x.shape)}"
            )
        # Project + positional-encode.
        projected = self._module.input_proj(x)
        pe = _SinusoidalPositionalEncoding.get(self.sequence_length, self.d_model)
        if pe.device != projected.device:
            pe = pe.to(projected.device)
        projected = projected + pe[:, : projected.size(1), :]
        encoded = self._module.encoder(projected)
        # Aggregate the sequence into a single feature vector. We use
        # mean pooling rather than [CLS] because the env observation
        # has no semantic anchor token — the mean is a stable summary
        # statistic over the lookback window.
        pooled = encoded.mean(dim=1)
        out = self._module.out_proj(pooled)
        return out

    @property
    def module(self) -> "nn.Module":
        return self._module

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "d_model": self.d_model,
                "n_heads": self.n_heads,
                "n_layers": self.n_layers,
                "d_ff": self.d_ff,
                "dropout": self.dropout,
            }
        )
        return out


__all__ = ["TransformerBackbone"]
