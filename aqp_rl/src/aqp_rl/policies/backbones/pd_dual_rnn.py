"""``PDDualRNNBackbone`` — OPD teacher-student dual-RNN with (μ, σ, V).

Port of ``trademaster/nets/pd.py::PDNet``: two parallel RNNs encode a
public + private state stream into separate hidden representations,
which are concatenated and projected onto ``(μ, σ, V)``.

Input layout
============

This backbone uses the same trick as :class:`HFTQBackbone`: the SB3
features extractor sees a flat observation, which we split into
``[public_state, private_state]`` using the configurable
``public_feature_dim`` / ``private_feature_dim`` constants.

Output: ``(B, 3)`` — ``[μ, σ, V]``. ``σ`` is positive via ``softplus``.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from aqp_rl.policies.backbones.base import TimeSeriesEncoder


class PDDualRNNBackbone(TimeSeriesEncoder):
    """OPD-style dual RNN backbone.

    Parameters
    ----------
    input_features:
        Public-state per-step feature count.
    sequence_length:
        Public-state stacked sequence length.
    output_dim:
        Fixed to 3 (``μ``, ``σ``, ``V``).
    private_feature_dim:
        Number of features per private-state row. Default ``2``
        (matches the canonical OPD ``[time_left, order_left]``).
    private_sequence_length:
        Stacked sequence length for the private state. Default equals
        ``sequence_length``.
    hidden_dim:
        RNN hidden width. Default ``64``.
    """

    rl_alias: ClassVar[str] = "pd_dual_rnn"
    rl_source: ClassVar[str] = "fang_2021"
    rl_category: ClassVar[str] = "execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("opd", "dual_rnn", "teacher_student")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int,
        output_dim: int = 3,
        private_feature_dim: int = 2,
        private_sequence_length: int | None = None,
        hidden_dim: int = 64,
        name: str | None = None,
    ) -> None:
        if output_dim != 3:
            raise ValueError(
                f"PDDualRNNBackbone output_dim is fixed at 3 (μ, σ, V); got {output_dim!r}"
            )
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        self.private_feature_dim = int(private_feature_dim)
        self.private_sequence_length = int(
            private_sequence_length if private_sequence_length is not None else sequence_length
        )
        self.hidden_dim = int(hidden_dim)
        self.rnn_public = nn.RNN(
            input_size=self.input_features,
            hidden_size=self.hidden_dim,
            num_layers=1,
            batch_first=True,
        )
        self.rnn_private = nn.RNN(
            input_size=self.private_feature_dim,
            hidden_size=self.hidden_dim,
            num_layers=1,
            batch_first=True,
        )
        self.L = nn.Linear(2 * self.hidden_dim, 2 * self.hidden_dim)
        self.mu_head = nn.Linear(2 * self.hidden_dim, 1)
        self.sigma_head = nn.Linear(2 * self.hidden_dim, 1)
        self.v_head = nn.Linear(2 * self.hidden_dim, 1)

    def forward(self, x: Any) -> torch.Tensor:
        tensor = _to_tensor(x)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        public_flat = self.input_features * self.sequence_length
        private_flat = self.private_feature_dim * self.private_sequence_length
        expected = public_flat + private_flat
        if tensor.shape[-1] == expected:
            public = tensor[:, :public_flat].reshape(-1, self.sequence_length, self.input_features)
            private = tensor[:, public_flat:].reshape(
                -1, self.private_sequence_length, self.private_feature_dim
            )
        else:
            # Fallback: only public ⇒ private = zeros (for smoke tests).
            public = tensor[:, :public_flat].reshape(-1, self.sequence_length, self.input_features)
            private = torch.zeros(
                public.shape[0],
                self.private_sequence_length,
                self.private_feature_dim,
                device=tensor.device,
                dtype=public.dtype,
            )
        return self.forward_split(public, private)

    def forward_split(
        self,
        public: torch.Tensor,
        private: torch.Tensor,
    ) -> torch.Tensor:
        _, h_pub = self.rnn_public(public)
        _, h_priv = self.rnn_private(private)
        h = torch.cat([h_pub.squeeze(0), h_priv.squeeze(0)], dim=-1)
        h = self.L(h)
        mu = torch.sigmoid(self.mu_head(h))
        sigma = F.softplus(self.sigma_head(h)) + 1e-3
        v = self.v_head(h)
        return torch.cat([mu, sigma, v], dim=-1)


def _to_tensor(x: Any) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.float()
    return torch.as_tensor(np.asarray(x), dtype=torch.float32)


__all__ = ["PDDualRNNBackbone"]
