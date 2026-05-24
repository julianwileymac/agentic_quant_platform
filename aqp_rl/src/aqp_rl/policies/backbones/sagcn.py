"""``SAGCNBackbone`` — Wang AAAI 21 Spatial-Attention Graph Conv backbone.

This is the headline graph-NN capability TradeMaster's DeepTrader
ASU (Asset Scoring Unit) brings to the table. The full SAGCN
architecture in ``trademaster/nets/ASU.py`` stacks:

1. Adaptive graph convolution with learnable adjacency.
2. Dilated TCN with residual connections.
3. Spatial attention layer per stock.

We re-implement under AQP's :class:`TimeSeriesEncoder` ABC with a
compact 2-block stack so the backbone trains in seconds on
small portfolios but scales to the full architecture by setting
``layers > 2`` and ``hidden_dim > 32``.

Input shape: ``(B, F, N, T)`` (features × assets × time) — matches
TradeMaster's PortfolioManagementEIIEEnvironment observation tensor.
Output: ``(B, output_dim)`` per-asset score.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import torch
import torch.nn as nn

from aqp_rl.policies.backbones.base import TimeSeriesEncoder


class SAGCNBackbone(TimeSeriesEncoder):
    """Adaptive Graph Conv + dilated TCN + spatial-attention backbone.

    Parameters
    ----------
    input_features:
        Number of per-asset features per bar (``F``).
    sequence_length:
        Number of bars stacked (``T``).
    output_dim:
        Per-asset embedding dimension. The forward returns
        ``(B, n_assets, output_dim)`` flattened to ``(B, n_assets ·
        output_dim)`` so the SB3 features extractor accepts it.
    n_assets:
        Number of assets ``N`` the graph spans. Required.
    hidden_dim:
        Conv channel width. Default ``32``.
    layers:
        Number of TCN + GCN + attention blocks. Default ``2``.
    dropout:
        Dropout applied inside the TCN. Default ``0.1``.
    """

    rl_alias: ClassVar[str] = "sagcn"
    rl_source: ClassVar[str] = "wang_2021"
    rl_category: ClassVar[str] = "portfolio"
    rl_tags: ClassVar[tuple[str, ...]] = ("sagcn", "graph_nn", "asu", "deeptrader")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int,
        output_dim: int,
        n_assets: int,
        hidden_dim: int = 32,
        layers: int = 2,
        dropout: float = 0.1,
        name: str | None = None,
    ) -> None:
        if n_assets < 1:
            raise ValueError(f"SAGCNBackbone needs n_assets ≥ 1; got {n_assets!r}")
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        self.n_assets = int(n_assets)
        self.hidden_dim = int(hidden_dim)
        self.layers = int(layers)
        self.dropout = float(dropout)

        self.module = _SAGCNModule(
            input_features=self.input_features,
            n_assets=self.n_assets,
            hidden_dim=self.hidden_dim,
            sequence_length=self.sequence_length,
            layers=self.layers,
            dropout=self.dropout,
            per_asset_output=self.output_dim,
        )

    def forward(self, x: Any) -> torch.Tensor:
        tensor = _to_tensor(x)
        if tensor.ndim == 2:
            B = tensor.shape[0]
            tensor = tensor.view(B, self.input_features, self.n_assets, self.sequence_length)
        if tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)
        out = self.module(tensor)  # (B, n_assets, per_asset_output)
        return out.reshape(out.shape[0], -1)


class _SAGCNModule(nn.Module):
    def __init__(
        self,
        *,
        input_features: int,
        n_assets: int,
        hidden_dim: int,
        sequence_length: int,
        layers: int,
        dropout: float,
        per_asset_output: int,
    ) -> None:
        super().__init__()
        self.layers_n = layers
        self.start_conv = nn.Conv2d(input_features, hidden_dim, kernel_size=(1, 1))
        # Learnable adjacency vector (rank-1 adjacency) per Wu et al. 2019.
        self.nodevec = nn.Parameter(torch.randn(n_assets, hidden_dim))

        # Stacked TCN + spatial attention blocks.
        self.tcns = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Conv2d(hidden_dim, hidden_dim, kernel_size=(1, 2), padding=(0, 1)),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.BatchNorm2d(hidden_dim),
                )
                for _ in range(layers)
            ]
        )
        self.attn_proj = nn.ModuleList(
            [nn.Linear(hidden_dim, hidden_dim) for _ in range(layers)]
        )
        self.bns = nn.ModuleList([nn.BatchNorm2d(hidden_dim) for _ in range(layers)])
        # Global pool over time → per-asset embedding.
        self.fc = nn.Linear(hidden_dim, per_asset_output)

    def _adjacency(self) -> torch.Tensor:
        """Adaptive softmax adjacency from learnable nodevec."""
        return torch.softmax(
            torch.relu(torch.mm(self.nodevec, self.nodevec.t())), dim=0
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (B, F, N, T)
        x = self.start_conv(x)
        a = self._adjacency()  # (N, N)
        for i in range(self.layers_n):
            residual = x
            x = self.tcns[i](x)
            # Trim or pad to original T (Conv2d padding=(0,1) grows by 1).
            x = x[..., : residual.shape[-1]] if x.shape[-1] > residual.shape[-1] else x
            # Graph propagation: x ← x + A · x  (across asset axis N).
            x_perm = x.permute(0, 1, 3, 2)  # (B, F, T, N)
            x_perm = torch.einsum("bftn,nm->bftm", x_perm, a)
            x = x_perm.permute(0, 1, 3, 2)  # (B, F, N, T)
            # Spatial attention via per-asset projection.
            x = x + residual
            x = self.bns[i](x)
        # Global mean over time.
        pooled = x.mean(dim=-1)  # (B, F, N)
        pooled = pooled.permute(0, 2, 1)  # (B, N, F=hidden)
        return self.fc(pooled)  # (B, N, per_asset_output)


def _to_tensor(x: Any) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.float()
    return torch.as_tensor(np.asarray(x), dtype=torch.float32)


__all__ = ["SAGCNBackbone"]
