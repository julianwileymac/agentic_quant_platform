"""``DualHeadContinuousBackbone`` — ETEO dual-head MLP (volume + price + V).

Port of ``trademaster/nets/eteo.py::ETEOStacked``. Takes a flattened
``(B, F · T)`` state and emits three heads:

- ``(B, 2)`` — Normal-distribution ``(μ, σ)`` for the action volume.
- ``(B, 2)`` — Normal-distribution ``(μ, σ)`` for the action price.
- ``(B, 1)`` — state-value ``V(s)``.

The forward returns a single ``(B, 5)`` concatenation
``[μ_v, σ_v, μ_p, σ_p, V]`` so the SB3 features extractor can consume
it as a flat vector. Downstream policies slice the heads explicitly.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import torch
import torch.nn as nn

from aqp_rl.policies.backbones.base import TimeSeriesEncoder


class DualHeadContinuousBackbone(TimeSeriesEncoder):
    """ETEO-style MLP with two action heads + value head.

    Parameters
    ----------
    input_features:
        Per-step state vector length.
    sequence_length:
        Number of bars stacked. Total flat input dim = ``input_features
        · sequence_length``.
    output_dim:
        Fixed to 5 (``μ_v, σ_v, μ_p, σ_p, V``). Other values raise.
    hidden_dims:
        Tuple of MLP layer widths. Default ``(64, 32)``.
    """

    rl_alias: ClassVar[str] = "eteo_dual_head"
    rl_source: ClassVar[str] = "lin_2020"
    rl_category: ClassVar[str] = "execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("eteo", "dual_head", "actor_critic")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int,
        output_dim: int = 5,
        hidden_dims: tuple[int, ...] = (64, 32),
        name: str | None = None,
    ) -> None:
        if output_dim != 5:
            raise ValueError(
                "DualHeadContinuousBackbone output_dim is fixed at 5 "
                f"(μ_v, σ_v, μ_p, σ_p, V); got {output_dim!r}"
            )
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        flat_dim = self.input_features * self.sequence_length
        layers: list[nn.Module] = []
        prev = flat_dim
        for h in hidden_dims:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            prev = h
        self.trunk = nn.Sequential(*layers)
        self.head_volume = nn.Linear(prev, 2)
        self.head_price = nn.Linear(prev, 2)
        self.head_value = nn.Linear(prev, 1)

    def forward(self, x: Any) -> torch.Tensor:
        tensor = _to_tensor(x)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        if tensor.ndim > 2:
            tensor = tensor.reshape(tensor.shape[0], -1)
        h = self.trunk(tensor)
        vol = self.head_volume(h)
        pri = self.head_price(h)
        v = self.head_value(h)
        return torch.cat([vol, pri, v], dim=-1)


def _to_tensor(x: Any) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.float()
    return torch.as_tensor(np.asarray(x), dtype=torch.float32)


__all__ = ["DualHeadContinuousBackbone"]
