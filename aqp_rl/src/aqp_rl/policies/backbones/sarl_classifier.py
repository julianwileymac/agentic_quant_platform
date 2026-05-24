"""``SARLClassifierBackbone`` — SARL auxiliary LSTM classifier.

Port of ``trademaster/nets/sarl.py::LSTMClf``. The SARL (Ye AAAI 20)
agent augments the RL state with a *direction-prediction* auxiliary
task: a small LSTM consumes the lookback window and produces a
probability vector over future-direction classes. The auxiliary
gradient regularises the shared feature representation.

This backbone is the auxiliary head — it takes ``(B, T, F)`` and
returns ``(B, output_dim)`` where ``output_dim`` is the number of
direction classes (default 2 for {up, down}). Use alongside another
backbone (e.g. :class:`RecurrentBackbone`) as the main encoder.
"""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from aqp_rl.policies.backbones.base import (
    TimeSeriesEncoder,
    reshape_obs_to_sequence,
)


class SARLClassifierBackbone(TimeSeriesEncoder):
    """SARL auxiliary LSTM classifier for direction prediction.

    Parameters
    ----------
    input_features:
        Per-step input feature count.
    sequence_length:
        Number of bars stacked.
    output_dim:
        Number of output classes. Default ``2`` (up / down).
    hidden_dim:
        LSTM hidden width.
    num_layers:
        LSTM depth.
    """

    rl_alias: ClassVar[str] = "sarl_lstm"
    rl_source: ClassVar[str] = "ye_2020"
    rl_category: ClassVar[str] = "auxiliary"
    rl_tags: ClassVar[tuple[str, ...]] = ("sarl", "lstm", "direction_classifier", "auxiliary_task")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int,
        output_dim: int = 2,
        hidden_dim: int = 32,
        num_layers: int = 1,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        self.hidden_dim = int(hidden_dim)
        self.num_layers = int(num_layers)
        self.lstm = nn.LSTM(
            input_size=self.input_features,
            hidden_size=self.hidden_dim,
            num_layers=self.num_layers,
            batch_first=True,
        )
        self.head = nn.Linear(self.hidden_dim, output_dim)

    def forward(self, x: Any) -> torch.Tensor:
        tensor = _to_tensor(x)
        if tensor.ndim == 2:
            tensor = reshape_obs_to_sequence(
                tensor.detach().cpu().numpy(),
                sequence_length=self.sequence_length,
                input_features=self.input_features,
            )
            tensor = torch.as_tensor(tensor, dtype=torch.float32)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
            tensor = reshape_obs_to_sequence(
                tensor.detach().cpu().numpy(),
                sequence_length=self.sequence_length,
                input_features=self.input_features,
            )
            tensor = torch.as_tensor(tensor, dtype=torch.float32)
        outputs, _ = self.lstm(tensor)
        last = outputs[:, -1, :]
        return F.softmax(self.head(last), dim=-1)


def _to_tensor(x: Any) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x.float()
    return torch.as_tensor(np.asarray(x), dtype=torch.float32)


__all__ = ["SARLClassifierBackbone"]
