"""``EIIEConvBackbone`` — Jiang & Liang 2017 Ensemble of Identical Independent Evaluators.

The canonical EIIE architecture is a per-asset 1-D conv over the
time-axis. The full TradeMaster reference (``trademaster/nets/eiie.py``)
applies two Conv2d stages with a learnable cash bias and softmaxes
across the asset dimension — we re-implement under AQP's
:class:`TimeSeriesEncoder` ABC, accepting either the canonical
``(B, F, N, T)`` input or the flat ``(B, F · N · T)`` collapse via
the shared reshape helper.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import torch
import torch.nn as nn

from aqp_rl.policies.backbones.base import (
    TimeSeriesEncoder,
    reshape_obs_to_sequence,
)


class EIIEConvBackbone(TimeSeriesEncoder):
    """EIIE-style per-asset conv + softmax-across-assets output.

    Parameters
    ----------
    input_features:
        Number of per-asset features per bar (``F``).
    sequence_length:
        Number of bars stacked into each observation (``T``).
    output_dim:
        Number of assets + 1 (cash slice). The output is a probability
        distribution over ``(cash, asset_1, …, asset_N)`` summing to 1.
    kernel_size:
        Time-axis kernel width for the first conv layer. Default ``3``.
    hidden_channels:
        Number of channels after the first conv. Default ``32``.
    """

    rl_alias: ClassVar[str] = "eiie_conv"
    rl_source: ClassVar[str] = "jiang_liang_2017"
    rl_category: ClassVar[str] = "portfolio"
    rl_tags: ClassVar[tuple[str, ...]] = ("eiie", "conv2d", "portfolio")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int,
        output_dim: int,
        kernel_size: int = 3,
        hidden_channels: int = 32,
        n_assets: int | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        # N assets is inferred from output_dim - 1 (cash slice) by default.
        self.n_assets = int(n_assets if n_assets is not None else output_dim - 1)
        if self.n_assets < 1:
            raise ValueError(
                f"EIIEConvBackbone needs n_assets ≥ 1; inferred {self.n_assets} from output_dim={output_dim}"
            )
        self.kernel_size = int(kernel_size)
        self.hidden_channels = int(hidden_channels)
        self.module = _EIIEConvModule(
            input_features=self.input_features,
            n_assets=self.n_assets,
            time_steps=self.sequence_length,
            kernel_size=self.kernel_size,
            hidden_channels=self.hidden_channels,
        )
        # Learnable cash bias appended before the final softmax.
        self.cash_bias = nn.Parameter(torch.zeros(1, 1))

    def forward(self, x: Any) -> torch.Tensor:
        tensor = _to_tensor(x)
        if tensor.ndim == 2:
            # Flat (B, F·N·T) — reshape to (B, F, N, T).
            B = tensor.shape[0]
            tensor = tensor.view(B, self.input_features, self.n_assets, self.sequence_length)
        if tensor.ndim == 3:
            # Single-batch (F, N, T) — promote to (1, F, N, T).
            tensor = tensor.unsqueeze(0)
        out = self.module(tensor)  # (B, n_assets)
        cash = self.cash_bias.expand(out.shape[0], 1)
        logits = torch.cat([cash, out], dim=1)  # (B, n_assets + 1)
        return torch.softmax(logits, dim=1)


class _EIIEConvModule(nn.Module):
    """Internal nn.Module that EIIEConvBackbone delegates to."""

    def __init__(
        self,
        *,
        input_features: int,
        n_assets: int,
        time_steps: int,
        kernel_size: int,
        hidden_channels: int,
    ) -> None:
        super().__init__()
        # Conv1: (B, F, N, T) → (B, hidden, N, T-k+1)
        self.conv1 = nn.Conv2d(
            in_channels=input_features,
            out_channels=hidden_channels,
            kernel_size=(1, kernel_size),
            padding=0,
        )
        # Conv2: (B, hidden, N, T-k+1) → (B, 1, N, 1)
        remaining = max(time_steps - kernel_size + 1, 1)
        self.conv2 = nn.Conv2d(
            in_channels=hidden_channels,
            out_channels=1,
            kernel_size=(1, remaining),
            padding=0,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.conv1(x))
        x = self.conv2(x)  # (B, 1, N, 1)
        return x.squeeze(-1).squeeze(1)  # (B, N)


def _to_tensor(x: Any) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.float()
    return torch.as_tensor(np.asarray(x), dtype=torch.float32)


__all__ = ["EIIEConvBackbone"]
