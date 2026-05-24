"""``HFTQBackbone`` — HFT_DDQN Q-network with previous-action embed + action mask.

Port of ``trademaster/nets/high_frequency_trading_dqn.py::HFTQNet``:
MLP backbone that consumes the LOB state + an embedding of the
previous discrete action, and produces Q-values masked by the env's
``available_action`` indicator (``+ (mask - 1) · max_punish``).

Input contract: this backbone exposes a multi-input ``forward`` that
accepts ``(state, previous_action, available_action)``. SB3 doesn't
natively pass auxiliary inputs to the features extractor, so the
recommended integration pattern is:

1. Wire the env so ``previous_action`` and ``available_action`` are
   concatenated onto the observation vector (the env's
   :class:`HighFrequencyTradingEnv` exposes them in ``info``, so
   the SB3 wrapper does the concat).
2. Pass ``previous_action_dim`` and ``available_action_dim`` to this
   constructor so it can slice them off the tail of the observation.

For pure-test invocation the multi-input ``forward`` is also exposed
directly via :meth:`forward_split`.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from aqp_rl.policies.backbones.base import TimeSeriesEncoder


class HFTQBackbone(TimeSeriesEncoder):
    """HFT Q-network with previous-action embedding + action masking.

    Parameters
    ----------
    input_features:
        State vector dimension (the LOB observation length excluding
        previous-action / mask tails).
    sequence_length:
        Set to ``1`` for the canonical flat HFT state.
    output_dim:
        Number of discrete actions (Q-values returned per action).
    embedding_dim:
        Embedding dim for the previous-action one-hot. Default ``32``.
    hidden_dim:
        MLP hidden width. Default ``64``.
    max_punish:
        Logit offset applied to masked actions. Default ``1e12``.
    """

    rl_alias: ClassVar[str] = "hft_qnet"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "hft"
    rl_tags: ClassVar[tuple[str, ...]] = ("hft", "dqn", "action_mask", "prev_action_embed")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int = 1,
        output_dim: int,
        embedding_dim: int = 32,
        hidden_dim: int = 64,
        max_punish: float = 1e12,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        self.embedding_dim = int(embedding_dim)
        self.hidden_dim = int(hidden_dim)
        self.max_punish = float(max_punish)
        self.fc1 = nn.Linear(input_features, hidden_dim)
        self.embed = nn.Embedding(output_dim, embedding_dim)
        self.fc2 = nn.Linear(hidden_dim + embedding_dim, hidden_dim)
        self.out = nn.Linear(hidden_dim, output_dim)

    def forward(self, x: Any) -> torch.Tensor:
        """Default forward: expects observation already concatenated.

        Layout of the input vector:

        ``[state_features (input_features), previous_action (1),
        available_action_mask (output_dim)]``

        Returns the masked Q-vector of shape ``(B, output_dim)``.
        """
        tensor = _to_tensor(x)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        expected = self.input_features + 1 + self.output_dim
        if tensor.shape[-1] != expected:
            # Fallback: assume only state was passed; previous_action=0
            # and full availability mask. Useful for smoke tests.
            B = tensor.shape[0]
            state = tensor[:, : self.input_features]
            prev_a = torch.zeros(B, dtype=torch.long, device=tensor.device)
            mask = torch.ones(B, self.output_dim, device=tensor.device)
        else:
            state = tensor[:, : self.input_features]
            prev_a = tensor[:, self.input_features].long()
            mask = tensor[:, self.input_features + 1 :]
        return self.forward_split(state, prev_a, mask)

    def forward_split(
        self,
        state: torch.Tensor,
        previous_action: torch.Tensor,
        available_action: torch.Tensor,
    ) -> torch.Tensor:
        """Three-input forward with explicit (state, prev_a, mask)."""
        h = F.relu(self.fc1(state))
        emb = self.embed(previous_action)
        h = torch.cat([h, emb], dim=-1)
        h = F.relu(self.fc2(h))
        q = self.out(h)
        masked_q = q + (available_action - 1.0) * self.max_punish
        return masked_q


def _to_tensor(x: Any) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.float()
    return torch.as_tensor(np.asarray(x), dtype=torch.float32)


__all__ = ["HFTQBackbone"]
