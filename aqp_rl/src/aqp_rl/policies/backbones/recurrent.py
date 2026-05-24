"""``RecurrentBackbone`` — LSTM / GRU / vanilla RNN encoder for RL policies.

Wraps PyTorch's built-in recurrent modules with the
:class:`TimeSeriesEncoder` contract. A single class supports all
three cell types via the ``cell`` kwarg so the spec's
``policy_backbone`` field can switch architectures without changing
class names.
"""
from __future__ import annotations

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


_CELL_FACTORIES: dict[str, str] = {
    "lstm": "LSTM",
    "gru": "GRU",
    "rnn": "RNN",
}


class RecurrentBackbone(TimeSeriesEncoder):
    """LSTM / GRU / vanilla-RNN sequence encoder.

    Parameters
    ----------
    cell:
        One of ``"lstm"`` / ``"gru"`` / ``"rnn"`` (case-insensitive).
    hidden_size:
        Recurrent hidden state dimensionality.
    num_layers:
        Stack depth.
    bidirectional:
        When ``True`` the recurrent stack runs both directions and
        the output dim doubles. Bidirectional encoding is anti-causal
        for live trading — only use during offline backtest training
        with an explicit awareness that the policy will see future
        information.
    dropout:
        Inter-layer dropout (no effect when ``num_layers=1``).
    """

    rl_alias: ClassVar[str] = "RecurrentBackbone"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "recurrent"
    rl_tags: ClassVar[tuple[str, ...]] = ("lstm", "gru", "rnn", "sequence")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int = 30,
        output_dim: int = 128,
        cell: str = "lstm",
        hidden_size: int = 128,
        num_layers: int = 1,
        bidirectional: bool = False,
        dropout: float = 0.0,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        if not _TORCH_AVAILABLE:
            raise ImportError("RecurrentBackbone requires torch")
        key = str(cell).lower()
        if key not in _CELL_FACTORIES:
            raise ValueError(f"Unknown recurrent cell {cell!r}; choose from {list(_CELL_FACTORIES)}")
        self.cell = key
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.bidirectional = bool(bidirectional)
        self.dropout = float(dropout)

        cell_cls = getattr(nn, _CELL_FACTORIES[self.cell])
        self._rnn = cell_cls(
            input_size=self.input_features,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            batch_first=True,
            bidirectional=self.bidirectional,
            dropout=self.dropout if self.num_layers > 1 else 0.0,
        )
        proj_in = self.hidden_size * (2 if self.bidirectional else 1)
        self._proj = nn.Linear(proj_in, self.output_dim)

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
        out, _ = self._rnn(x)
        # Take the last hidden state (causal: the most-recent bar's
        # representation). For bidirectional we concatenate the last
        # step of the forward direction with the first step of the
        # backward direction.
        if self.bidirectional:
            fwd = out[:, -1, : self.hidden_size]
            bwd = out[:, 0, self.hidden_size :]
            pooled = torch.cat([fwd, bwd], dim=-1)
        else:
            pooled = out[:, -1, :]
        return self._proj(pooled)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "cell": self.cell,
                "hidden_size": self.hidden_size,
                "num_layers": self.num_layers,
                "bidirectional": self.bidirectional,
                "dropout": self.dropout,
            }
        )
        return out


__all__ = ["RecurrentBackbone"]
