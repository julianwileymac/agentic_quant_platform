"""SPM forecaster ports — PyTorch implementations.

All inherit :class:`aqp.ml.models.spm._torch_base.TorchForecasterBase`
which provides the training loop. Subclasses implement
:meth:`build_module` returning a ``torch.nn.Module``.

PyTorch is imported lazily inside :meth:`build_module` so callers that
never instantiate a model don't pull torch.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from aqp.core.registry import register
from aqp.ml.models.spm._torch_base import TorchForecasterBase

logger = logging.getLogger(__name__)


def _t():
    """Lazy torch import (returns ``(torch, nn)``)."""
    import torch
    from torch import nn
    return torch, nn


# ---------------------------------------------------------------------------
# RNN family
# ---------------------------------------------------------------------------


@register("LSTMForecaster", source="stock_prediction_models", category="rnn", kind="model")
class LSTMForecaster(TorchForecasterBase):
    """Single-layer LSTM forecaster — direct port of SPM 1.lstm.ipynb."""

    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features: int, hidden_size: int, dropout: float):
                super().__init__()
                self.lstm = nn.LSTM(n_features, hidden_size, batch_first=True, dropout=dropout)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


@register("BidirectionalLSTM", source="stock_prediction_models", category="rnn", kind="model")
class BidirectionalLSTM(TorchForecasterBase):
    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, dropout):
                super().__init__()
                self.lstm = nn.LSTM(n_features, hidden_size, batch_first=True, bidirectional=True, dropout=dropout)
                self.head = nn.Linear(2 * hidden_size, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


@register("LSTMAttention", source="stock_prediction_models", category="rnn_attention", kind="model")
class LSTMAttention(TorchForecasterBase):
    """LSTM with scaled-dot-product attention pooling."""

    def build_module(self):
        torch, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, dropout):
                super().__init__()
                self.lstm = nn.LSTM(n_features, hidden_size, batch_first=True, dropout=dropout)
                self.attn = nn.Linear(hidden_size, 1)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, _ = self.lstm(x)  # (B, T, H)
                weights = torch.softmax(self.attn(out).squeeze(-1), dim=-1)  # (B, T)
                pooled = (out * weights.unsqueeze(-1)).sum(dim=1)
                return self.head(pooled)

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


@register("StackedLSTM", source="stock_prediction_models", category="rnn", kind="model")
class StackedLSTM(TorchForecasterBase):
    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, num_layers, dropout):
                super().__init__()
                self.lstm = nn.LSTM(
                    n_features, hidden_size, num_layers=max(num_layers, 2),
                    batch_first=True, dropout=dropout,
                )
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.num_layers, cfg.dropout)


@register("GRUForecaster", source="stock_prediction_models", category="rnn", kind="model")
class GRUForecaster(TorchForecasterBase):
    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, dropout):
                super().__init__()
                self.gru = nn.GRU(n_features, hidden_size, batch_first=True, dropout=dropout)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, _ = self.gru(x)
                return self.head(out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


@register("BidirectionalGRU", source="stock_prediction_models", category="rnn", kind="model")
class BidirectionalGRU(TorchForecasterBase):
    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, dropout):
                super().__init__()
                self.gru = nn.GRU(n_features, hidden_size, batch_first=True, bidirectional=True, dropout=dropout)
                self.head = nn.Linear(2 * hidden_size, 1)

            def forward(self, x):
                out, _ = self.gru(x)
                return self.head(out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


@register("VanillaRNN", source="stock_prediction_models", category="rnn", kind="model")
class VanillaRNN(TorchForecasterBase):
    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, dropout):
                super().__init__()
                self.rnn = nn.RNN(n_features, hidden_size, batch_first=True, dropout=dropout, nonlinearity="tanh")
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, _ = self.rnn(x)
                return self.head(out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


@register("LSTMGRUHybrid", source="stock_prediction_models", category="rnn", kind="model")
class LSTMGRUHybrid(TorchForecasterBase):
    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, dropout):
                super().__init__()
                self.lstm = nn.LSTM(n_features, hidden_size, batch_first=True, dropout=dropout)
                self.gru = nn.GRU(hidden_size, hidden_size, batch_first=True, dropout=dropout)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                gru_out, _ = self.gru(lstm_out)
                return self.head(gru_out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


# ---------------------------------------------------------------------------
# Conv / TCN
# ---------------------------------------------------------------------------


@register("Conv1DForecaster", source="stock_prediction_models", category="conv", kind="model")
class Conv1DForecaster(TorchForecasterBase):
    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size):
                super().__init__()
                self.conv = nn.Conv1d(n_features, hidden_size, kernel_size=3, padding=1)
                self.pool = nn.AdaptiveAvgPool1d(1)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                # input: (B, T, F) -> conv expects (B, F, T)
                x = x.transpose(1, 2)
                x = self.conv(x).relu()
                x = self.pool(x).squeeze(-1)
                return self.head(x)

        return _Net(cfg.n_features, cfg.hidden_size)


@register("TCNForecaster", source="stock_prediction_models", category="conv", kind="model")
class TCNForecaster(TorchForecasterBase):
    """Temporal Convolutional Network — dilated causal 1D convs."""

    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _CausalConv(nn.Module):
            def __init__(self, channels, kernel_size, dilation):
                super().__init__()
                self.pad = (kernel_size - 1) * dilation
                self.conv = nn.Conv1d(channels, channels, kernel_size, padding=self.pad, dilation=dilation)
                self.relu = nn.ReLU()

            def forward(self, x):
                out = self.conv(x)
                if self.pad > 0:
                    out = out[:, :, : -self.pad]
                return self.relu(out)

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, num_layers):
                super().__init__()
                self.proj = nn.Conv1d(n_features, hidden_size, 1)
                self.blocks = nn.ModuleList([_CausalConv(hidden_size, 2, 2 ** i) for i in range(num_layers)])
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                x = x.transpose(1, 2)  # (B, F, T)
                x = self.proj(x)
                for block in self.blocks:
                    x = x + block(x)
                return self.head(x[:, :, -1])

        return _Net(cfg.n_features, cfg.hidden_size, max(cfg.num_layers, 3))


# ---------------------------------------------------------------------------
# Transformer family
# ---------------------------------------------------------------------------


@register("TransformerForecaster", source="stock_prediction_models", category="transformer", kind="model")
class TransformerForecaster(TorchForecasterBase):
    """Encoder-only transformer (small)."""

    def build_module(self):
        torch, nn = _t()
        cfg = self.config

        class _PosEnc(nn.Module):
            def __init__(self, d_model, max_len=5000):
                super().__init__()
                pe = torch.zeros(max_len, d_model)
                position = torch.arange(0, max_len).unsqueeze(1).float()
                div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
                pe[:, 0::2] = torch.sin(position * div_term)
                pe[:, 1::2] = torch.cos(position * div_term)
                self.register_buffer("pe", pe.unsqueeze(0))

            def forward(self, x):
                return x + self.pe[:, : x.size(1)]

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, num_layers):
                super().__init__()
                self.proj = nn.Linear(n_features, hidden_size)
                self.pos = _PosEnc(hidden_size)
                layer = nn.TransformerEncoderLayer(hidden_size, nhead=4, dim_feedforward=hidden_size * 2, batch_first=True)
                self.encoder = nn.TransformerEncoder(layer, num_layers=max(num_layers, 1))
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                x = self.proj(x)
                x = self.pos(x)
                x = self.encoder(x)
                return self.head(x[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.num_layers)


@register("AttentionOnlyForecaster", source="stock_prediction_models", category="transformer", kind="model")
class AttentionOnlyForecaster(TorchForecasterBase):
    """Single multi-head self-attention block + linear head."""

    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size):
                super().__init__()
                self.proj = nn.Linear(n_features, hidden_size)
                self.attn = nn.MultiheadAttention(hidden_size, num_heads=4, batch_first=True)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                x = self.proj(x)
                attn_out, _ = self.attn(x, x, x)
                return self.head(attn_out[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size)


@register("BERTForecaster", source="stock_prediction_models", category="transformer", kind="model")
class BERTForecaster(TorchForecasterBase):
    """Distilled BERT-style encoder (CPU-friendly: 2 layers, 64 hidden)."""

    def build_module(self):
        _, nn = _t()
        cfg = self.config
        # Force a small config so this stays trainable on CPU.
        cfg.hidden_size = min(cfg.hidden_size, 64)
        cfg.num_layers = min(cfg.num_layers, 2)

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, num_layers):
                super().__init__()
                self.proj = nn.Linear(n_features, hidden_size)
                self.norm = nn.LayerNorm(hidden_size)
                layer = nn.TransformerEncoderLayer(hidden_size, nhead=4, dim_feedforward=hidden_size * 2, batch_first=True)
                self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                x = self.proj(x)
                x = self.norm(x)
                x = self.encoder(x)
                return self.head(x[:, -1, :])

        return _Net(cfg.n_features, cfg.hidden_size, cfg.num_layers)


# ---------------------------------------------------------------------------
# Bayesian
# ---------------------------------------------------------------------------


@register("MonteCarloDropoutForecaster", source="stock_prediction_models", category="bayesian", kind="model")
class MonteCarloDropoutForecaster(TorchForecasterBase):
    """LSTM with dropout enabled at inference for predictive variance.

    Override :meth:`predict_with_uncertainty` to draw N stochastic
    forward passes; ``predict`` returns the mean.
    """

    def build_module(self):
        _, nn = _t()
        cfg = self.config

        class _Net(nn.Module):
            def __init__(self, n_features, hidden_size, dropout):
                super().__init__()
                self.lstm = nn.LSTM(n_features, hidden_size, batch_first=True)
                self.dropout = nn.Dropout(max(dropout, 0.2))
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(self.dropout(out[:, -1, :]))

        return _Net(cfg.n_features, cfg.hidden_size, cfg.dropout)


__all__ = [
    "AttentionOnlyForecaster",
    "BERTForecaster",
    "BidirectionalGRU",
    "BidirectionalLSTM",
    "Conv1DForecaster",
    "GRUForecaster",
    "LSTMAttention",
    "LSTMForecaster",
    "LSTMGRUHybrid",
    "MonteCarloDropoutForecaster",
    "StackedLSTM",
    "TCNForecaster",
    "TransformerForecaster",
    "VanillaRNN",
]
