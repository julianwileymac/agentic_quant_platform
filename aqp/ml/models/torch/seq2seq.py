"""Seq2Seq family — ports of the Stock-Prediction-Models notebook zoo.

All five variants fit the ``BaseTorchModel`` training loop: they consume
``(B, step_len, F)`` windows and output a scalar prediction per sample
(one-step-ahead forecast trained with MSE on the label ``LABEL0``).

Source: ``inspiration/Stock-Prediction-Models-master/deep-learning/``.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


def _encoder_decoder(torch, nn, rnn_cls, in_f, hidden, layers, dropout):
    class _Seq2Seq(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = rnn_cls(
                in_f,
                hidden,
                num_layers=layers,
                dropout=dropout if layers > 1 else 0.0,
                batch_first=True,
            )
            self.decoder = rnn_cls(
                hidden,
                hidden,
                num_layers=layers,
                dropout=dropout if layers > 1 else 0.0,
                batch_first=True,
            )
            self.head = nn.Linear(hidden, 1)

        def forward(self, x):
            enc_out, state = self.encoder(x)
            dec_in = enc_out[:, -1:, :]
            dec_out, _ = self.decoder(dec_in, state)
            return self.head(dec_out[:, -1, :]).squeeze(-1)

    return _Seq2Seq()


@register("LSTMSeq2Seq")
class LSTMSeq2Seq(BaseTorchModel):
    """Classic LSTM encoder → LSTM decoder forecaster."""

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        return _encoder_decoder(
            torch, torch.nn, torch.nn.LSTM, input_size,
            self.hidden_size, self.num_layers, self.dropout,
        )


@register("GRUSeq2Seq")
class GRUSeq2Seq(LSTMSeq2Seq):
    """GRU encoder → GRU decoder forecaster."""

    def build_module(self, input_size: int):
        torch = _import_torch()
        return _encoder_decoder(
            torch, torch.nn, torch.nn.GRU, input_size,
            self.hidden_size, self.num_layers, self.dropout,
        )


@register("LSTMSeq2SeqVAE")
class LSTMSeq2SeqVAE(BaseTorchModel):
    """LSTM Seq2Seq + VAE latent bottleneck.

    The decoder is conditioned on a reparameterised latent drawn from the
    encoder's final hidden state. Trained with MSE on the label and a
    KL-divergence regulariser (the KL term is summed into the MSE loss via
    the training-loop loss hook — here we just expose a latent path).
    """

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        latent_size: int = 16,
        num_layers: int = 1,
        dropout: float = 0.1,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.latent_size = int(latent_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _VAE(nn.Module):
            def __init__(self, in_f, hidden, latent, layers, dropout):
                super().__init__()
                self.encoder = nn.LSTM(
                    in_f, hidden, num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0, batch_first=True,
                )
                self.mu = nn.Linear(hidden, latent)
                self.logvar = nn.Linear(hidden, latent)
                self.decoder_init = nn.Linear(latent, hidden)
                self.decoder = nn.LSTM(
                    hidden, hidden, num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0, batch_first=True,
                )
                self.head = nn.Linear(hidden, 1)

            def forward(self, x):
                enc_out, _ = self.encoder(x)
                last = enc_out[:, -1, :]
                mu = self.mu(last)
                logvar = self.logvar(last)
                std = (0.5 * logvar).exp()
                z = mu + std * torch.randn_like(std)
                h0 = self.decoder_init(z).unsqueeze(0).repeat(self.decoder.num_layers, 1, 1)
                c0 = torch.zeros_like(h0)
                dec_in = last.unsqueeze(1)
                out, _ = self.decoder(dec_in, (h0, c0))
                return self.head(out[:, -1, :]).squeeze(-1)

        return _VAE(
            input_size,
            self.hidden_size,
            self.latent_size,
            self.num_layers,
            self.dropout,
        )


@register("DilatedCNNSeq2Seq")
class DilatedCNNSeq2Seq(BaseTorchModel):
    """Dilated-CNN encoder with a small GRU decoder head."""

    is_sequence = True

    def __init__(
        self,
        channels: list[int] | None = None,
        kernel_size: int = 3,
        hidden_size: int = 64,
        dropout: float = 0.1,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.channels = list(channels or [32, 64])
        self.kernel_size = int(kernel_size)
        self.hidden_size = int(hidden_size)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _DilatedBlock(nn.Module):
            def __init__(self, in_c, out_c, k, dilation):
                super().__init__()
                self.pad = (k - 1) * dilation
                self.conv = nn.Conv1d(in_c, out_c, k, padding=self.pad, dilation=dilation)
                self.act = nn.GELU()

            def forward(self, x):
                return self.act(self.conv(x)[..., : x.size(-1)])

        class _Model(nn.Module):
            def __init__(self, in_f, chs, k, hidden, dropout):
                super().__init__()
                blocks: list[nn.Module] = []
                prev = in_f
                for i, c in enumerate(chs):
                    blocks.append(_DilatedBlock(prev, c, k, dilation=2**i))
                    prev = c
                self.encoder = nn.Sequential(*blocks)
                self.decoder = nn.GRU(prev, hidden, num_layers=1, batch_first=True)
                self.drop = nn.Dropout(dropout)
                self.head = nn.Linear(hidden, 1)

            def forward(self, x):
                # (B, T, F) -> (B, F, T)
                x = x.transpose(1, 2)
                h = self.encoder(x).transpose(1, 2)
                out, _ = self.decoder(h)
                return self.head(self.drop(out[:, -1, :])).squeeze(-1)

        return _Model(
            input_size, self.channels, self.kernel_size, self.hidden_size, self.dropout
        )


@register("TransformerForecaster")
class TransformerForecaster(BaseTorchModel):
    """Attention-is-all-you-need-style encoder for one-step forecasting."""

    is_sequence = True

    def __init__(
        self,
        d_model: int = 64,
        n_heads: int = 4,
        num_layers: int = 3,
        dim_feedforward: int = 128,
        dropout: float = 0.1,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.d_model = int(d_model)
        self.n_heads = int(n_heads)
        self.num_layers = int(num_layers)
        self.dim_feedforward = int(dim_feedforward)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _Former(nn.Module):
            def __init__(self, in_f, d_model, heads, layers, ff, dropout, step_len):
                super().__init__()
                self.proj = nn.Linear(in_f, d_model)
                self.pos = nn.Parameter(torch.randn(1, step_len, d_model) * 0.02)
                layer = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=heads, dim_feedforward=ff,
                    dropout=dropout, batch_first=True,
                )
                self.enc = nn.TransformerEncoder(layer, num_layers=layers)
                self.head = nn.Sequential(nn.Linear(d_model, d_model), nn.GELU(), nn.Linear(d_model, 1))

            def forward(self, x):
                h = self.proj(x) + self.pos[:, : x.size(1), :]
                h = self.enc(h)
                pooled = h.mean(dim=1)
                return self.head(pooled).squeeze(-1)

        return _Former(
            input_size, self.d_model, self.n_heads, self.num_layers,
            self.dim_feedforward, self.dropout, self.step_len,
        )


__all__ = [
    "DilatedCNNSeq2Seq",
    "GRUSeq2Seq",
    "LSTMSeq2Seq",
    "LSTMSeq2SeqVAE",
    "TransformerForecaster",
]
