"""``MarketScorerBackbone`` — DeepTrader MSU (Market Scoring Unit).

Port of ``trademaster/nets/MSU.py``: LSTM + attention head that
encodes a global market-level time series into a Gaussian
``(μ, σ)`` over the portfolio-risk parameter ``ρ``. Used by the
:class:`DeepTraderAgent` to scale long-vs-short portfolio exposure.

Input: ``(B, T, F)`` global market features.
Output: ``(B, 2)`` — concatenated ``(μ, log_σ)`` of the Normal.
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


class MarketScorerBackbone(TimeSeriesEncoder):
    """LSTM + attention → ``(μ, σ)`` market scorer.

    Parameters
    ----------
    input_features:
        Per-step market feature count.
    sequence_length:
        Number of bars stacked.
    output_dim:
        Forced to 2 (``μ``, ``log_σ``). Other values raise.
    hidden_dim:
        LSTM hidden width. Default ``64``.
    """

    rl_alias: ClassVar[str] = "market_scorer"
    rl_source: ClassVar[str] = "wang_2021"
    rl_category: ClassVar[str] = "portfolio"
    rl_tags: ClassVar[tuple[str, ...]] = ("msu", "market_scorer", "lstm", "deeptrader")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int,
        output_dim: int = 2,
        hidden_dim: int = 64,
        name: str | None = None,
    ) -> None:
        if output_dim != 2:
            raise ValueError(
                f"MarketScorerBackbone output_dim is fixed at 2 (μ, log σ); got {output_dim!r}"
            )
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        self.hidden_dim = int(hidden_dim)
        self.lstm = nn.LSTM(
            input_size=self.input_features,
            hidden_size=self.hidden_dim,
            num_layers=1,
            batch_first=True,
        )
        self.attn_w1 = nn.Linear(2 * self.hidden_dim, self.hidden_dim)
        self.attn_w2 = nn.Linear(self.hidden_dim, 1)
        self.linear1 = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.linear2 = nn.Linear(self.hidden_dim, 2)
        self.bn = nn.BatchNorm1d(self.hidden_dim)

    def forward(self, x: Any) -> torch.Tensor:
        tensor = _to_tensor(x)
        if tensor.ndim == 2:
            # Could be (B, T·F) — try to reshape to (B, T, F).
            tensor = reshape_obs_to_sequence(
                tensor.detach().cpu().numpy(),
                sequence_length=self.sequence_length,
                input_features=self.input_features,
            )
            tensor = torch.as_tensor(tensor, dtype=torch.float32)
        outputs, (h_n, _) = self.lstm(tensor)
        # Attention over time using final hidden state as the query.
        h_rep = h_n[-1].unsqueeze(1).repeat(1, outputs.shape[1], 1)  # (B, T, H)
        cat = torch.cat([outputs, h_rep], dim=-1)  # (B, T, 2H)
        scores = self.attn_w2(torch.tanh(self.attn_w1(cat))).squeeze(-1)  # (B, T)
        attn_weights = torch.softmax(scores, dim=-1).unsqueeze(1)  # (B, 1, T)
        attn_embed = torch.bmm(attn_weights, outputs).squeeze(1)  # (B, H)
        # BatchNorm needs at least 2 elements along the batch dim.
        if attn_embed.shape[0] > 1:
            attn_embed = self.bn(attn_embed)
        embed = torch.relu(self.linear1(attn_embed))
        out = self.linear2(embed)
        # Reparameterise log-σ for numerical stability.
        return out


def _to_tensor(x: Any) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.float()
    return torch.as_tensor(np.asarray(x), dtype=torch.float32)


__all__ = ["MarketScorerBackbone"]
