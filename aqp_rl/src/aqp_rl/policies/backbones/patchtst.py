"""``PatchTSTBackbone`` — patch-based time-series Transformer (Nie 2023).

Replaces per-bar Transformer tokens with non-overlapping patches of
the lookback window. Each patch of ``patch_length`` bars is linearly
projected to ``d_model`` and treated as a single token by the
Transformer encoder, dramatically reducing token count for long
horizons (e.g. 252-day lookback -> 21 patches at length 12).

Reference: Nie et al. "A Time Series is Worth 64 Words" (ICLR 2023).
A heavier HuggingFace wrapper (with positional + temporal embeddings)
lives at ``aqp/ml/models/huggingface.py``; this implementation is the
lean RL-friendly variant intended for online inference.
"""
from __future__ import annotations

import math
from typing import Any, ClassVar

import numpy as np

from aqp_rl.policies.backbones.base import TimeSeriesEncoder, reshape_obs_to_sequence

try:
    import torch
    from torch import nn

    _TORCH_AVAILABLE = True
except Exception:
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False


class PatchTSTBackbone(TimeSeriesEncoder):
    """Patch-tokenised time-series Transformer encoder.

    Parameters
    ----------
    patch_length:
        Number of bars per patch. ``sequence_length`` must be a
        multiple of ``patch_length`` (we right-trim otherwise).
        Default 4 → for a 32-bar lookback that's 8 tokens.
    stride:
        Patch stride. Defaults to ``patch_length`` for non-overlapping
        patches; set < ``patch_length`` for overlapping patches.
    d_model:
        Patch embedding dim. Default 64.
    n_heads:
        Number of attention heads. Must divide ``d_model``.
    n_layers:
        Transformer encoder layer count.
    d_ff:
        Feedforward dim inside the Transformer encoder.
    dropout:
        Inter-layer dropout.
    """

    rl_alias: ClassVar[str] = "PatchTSTBackbone"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "transformer"
    rl_tags: ClassVar[tuple[str, ...]] = ("patchtst", "transformer", "patches", "long_horizon")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int = 32,
        output_dim: int = 128,
        patch_length: int = 4,
        stride: int | None = None,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        d_ff: int = 128,
        dropout: float = 0.1,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        if not _TORCH_AVAILABLE:
            raise ImportError("PatchTSTBackbone requires torch")
        if patch_length <= 0:
            raise ValueError("patch_length must be positive")
        self.patch_length = int(patch_length)
        self.stride = int(stride or patch_length)
        # Ensure d_model is divisible by n_heads.
        if d_model % n_heads != 0:
            d_model = int(math.ceil(d_model / n_heads) * n_heads)
        self.d_model = int(d_model)
        self.n_heads = int(n_heads)
        self.n_layers = int(n_layers)
        self.d_ff = int(d_ff)
        self.dropout = float(dropout)

        self._patch_proj = nn.Linear(self.patch_length * self.input_features, self.d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=self.d_model,
            nhead=self.n_heads,
            dim_feedforward=self.d_ff,
            dropout=self.dropout,
            batch_first=True,
        )
        self._encoder = nn.TransformerEncoder(encoder_layer, num_layers=self.n_layers)
        self._proj = nn.Linear(self.d_model, self.output_dim)
        self.num_patches = self._compute_num_patches(self.sequence_length, self.patch_length, self.stride)
        if self.num_patches < 1:
            raise ValueError(
                f"PatchTSTBackbone: sequence_length={self.sequence_length} too short for "
                f"patch_length={self.patch_length} stride={self.stride}"
            )

    @staticmethod
    def _compute_num_patches(seq_len: int, patch_length: int, stride: int) -> int:
        return max(0, (seq_len - patch_length) // stride + 1)

    def _patchify(self, x: "torch.Tensor") -> "torch.Tensor":
        """Slice (B, L, F) into (B, num_patches, patch_length * F)."""
        b, l, f = x.shape
        patches = []
        for start in range(0, l - self.patch_length + 1, self.stride):
            patches.append(x[:, start : start + self.patch_length, :].reshape(b, -1))
        return torch.stack(patches, dim=1)

    def forward(self, x: Any) -> "torch.Tensor":
        if not _TORCH_AVAILABLE:
            raise ImportError("torch required at inference time")
        if isinstance(x, np.ndarray):
            x = reshape_obs_to_sequence(
                x, sequence_length=self.sequence_length, input_features=self.input_features
            )
            x = torch.from_numpy(x.astype(np.float32))
        elif isinstance(x, torch.Tensor) and x.dim() == 2:
            arr = x.detach().cpu().numpy()
            arr = reshape_obs_to_sequence(
                arr,
                sequence_length=self.sequence_length,
                input_features=self.input_features,
            )
            x = torch.from_numpy(arr.astype(np.float32)).to(x.device)
        patched = self._patchify(x)
        embedded = self._patch_proj(patched)
        encoded = self._encoder(embedded)
        pooled = encoded.mean(dim=1)
        return self._proj(pooled)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "patch_length": self.patch_length,
                "stride": self.stride,
                "d_model": self.d_model,
                "n_heads": self.n_heads,
                "n_layers": self.n_layers,
                "d_ff": self.d_ff,
                "dropout": self.dropout,
                "num_patches": self.num_patches,
            }
        )
        return out


__all__ = ["PatchTSTBackbone"]
