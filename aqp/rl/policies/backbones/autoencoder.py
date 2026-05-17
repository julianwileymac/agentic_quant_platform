"""``AutoencoderBackbone`` — encoder-only feature extractor for RL policies.

Compresses a high-dimensional observation (concatenated per-asset
OHLCV + indicators + portfolio state, often 500-2000 features) into
a low-dimensional bottleneck (typically 32-128 dims) which the
policy network consumes.

Two operating modes:

- ``pretrained=False`` (default): trains the encoder jointly with
  the RL policy. The decoder is dropped (we keep only the encoder
  for inference).
- ``pretrained=True``: loads weights from a sibling
  :class:`aqp.ml.models.ensemble.AutoEncoderDNNStack` checkpoint
  (which has been trained on a reconstruction loss against the
  silver-tier feature snapshot). The encoder is frozen by default
  — set ``freeze_encoder=False`` to fine-tune.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from aqp.rl.policies.backbones.base import TimeSeriesEncoder

logger = logging.getLogger(__name__)

try:
    import torch
    from torch import nn

    _TORCH_AVAILABLE = True
except Exception:
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False


def _make_mlp(sizes: list[int], *, activation: type, dropout: float = 0.0) -> "nn.Sequential":
    layers: list = []
    for i in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[i], sizes[i + 1]))
        if i < len(sizes) - 2:
            layers.append(activation())
            if dropout > 0.0:
                layers.append(nn.Dropout(dropout))
    return nn.Sequential(*layers)


class AutoencoderBackbone(TimeSeriesEncoder):
    """Bottleneck encoder feeding a fixed-dim feature vector to the policy.

    The autoencoder treats the observation as a flat vector — no
    sequence reshaping happens here. Set ``sequence_length=1`` and
    ``input_features=D`` (the flat observation dimensionality).

    Parameters
    ----------
    hidden_dims:
        Encoder layer widths excluding input + output. Default
        ``[256, 128]`` gives ``input -> 256 -> 128 -> bottleneck``.
    bottleneck_dim:
        The latent code size. ``output_dim`` matches this when no
        post-encoder projection is wanted; pass a separate
        ``output_dim`` to add a final linear projection.
    activation:
        ``"relu"`` (default) / ``"gelu"`` / ``"silu"``.
    dropout:
        Inter-layer dropout (default 0.1).
    pretrained_path:
        Optional path to a saved ``AutoEncoderDNNStack`` checkpoint
        — see :mod:`aqp.ml.models.ensemble`. When supplied the
        encoder loads its weights; the freeze flag controls whether
        gradients flow during RL training.
    freeze_encoder:
        When ``True`` (default with ``pretrained=True``) the encoder
        is frozen and only the projection head trains.
    """

    rl_alias: ClassVar[str] = "AutoencoderBackbone"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "autoencoder"
    rl_tags: ClassVar[tuple[str, ...]] = ("autoencoder", "encoder_only", "feature_extractor")

    def __init__(
        self,
        *,
        input_features: int,
        sequence_length: int = 1,
        output_dim: int = 128,
        hidden_dims: list[int] | None = None,
        bottleneck_dim: int | None = None,
        activation: str = "relu",
        dropout: float = 0.1,
        pretrained_path: str | None = None,
        freeze_encoder: bool | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input_features=input_features,
            sequence_length=sequence_length,
            output_dim=output_dim,
            name=name,
        )
        if not _TORCH_AVAILABLE:
            raise ImportError("AutoencoderBackbone requires torch")
        self.hidden_dims = list(hidden_dims or [256, 128])
        self.bottleneck_dim = int(bottleneck_dim or output_dim)
        act_cls = {
            "relu": nn.ReLU,
            "gelu": nn.GELU,
            "silu": nn.SiLU,
        }.get(str(activation).lower(), nn.ReLU)
        self.activation_name = str(activation)
        self.dropout = float(dropout)

        encoder_sizes = [input_features * sequence_length, *self.hidden_dims, self.bottleneck_dim]
        self._encoder = _make_mlp(encoder_sizes, activation=act_cls, dropout=self.dropout)
        # Optional projection if output_dim != bottleneck.
        if self.bottleneck_dim != output_dim:
            self._proj = nn.Linear(self.bottleneck_dim, output_dim)
        else:
            self._proj = nn.Identity()

        self.pretrained_path: str | None = str(pretrained_path) if pretrained_path else None
        self.freeze_encoder: bool = bool(
            freeze_encoder if freeze_encoder is not None else bool(pretrained_path)
        )
        if self.pretrained_path:
            self._load_pretrained_weights(self.pretrained_path)
        if self.freeze_encoder:
            for p in self._encoder.parameters():
                p.requires_grad = False

    def _load_pretrained_weights(self, path: str) -> None:
        ckpt_path = Path(path)
        if not ckpt_path.exists():
            logger.warning(
                "AutoencoderBackbone: pretrained checkpoint %s not found; training from scratch",
                path,
            )
            return
        try:
            state = torch.load(str(ckpt_path), map_location="cpu")
            # Allow either a raw state_dict or a dict carrying it.
            if isinstance(state, dict) and "encoder_state_dict" in state:
                self._encoder.load_state_dict(state["encoder_state_dict"])
            else:
                self._encoder.load_state_dict(state)
            logger.info("AutoencoderBackbone: loaded pretrained weights from %s", path)
        except Exception:
            logger.exception(
                "AutoencoderBackbone: failed to load pretrained weights from %s; training from scratch",
                path,
            )

    def forward(self, x: Any) -> "torch.Tensor":
        if not _TORCH_AVAILABLE:
            raise ImportError("torch required at inference time")
        if isinstance(x, np.ndarray):
            arr = x.astype(np.float32)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            x = torch.from_numpy(arr)
        elif isinstance(x, torch.Tensor) and x.dim() == 1:
            x = x.unsqueeze(0)
        if isinstance(x, torch.Tensor) and x.dim() == 3:
            # Flatten (B, L, F) -> (B, L*F) so the MLP encoder can
            # ingest. The autoencoder treats temporal structure as
            # part of the input vector rather than as a sequence.
            x = x.reshape(x.shape[0], -1)
        latent = self._encoder(x)
        return self._proj(latent)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "hidden_dims": list(self.hidden_dims),
                "bottleneck_dim": self.bottleneck_dim,
                "activation": self.activation_name,
                "dropout": self.dropout,
                "pretrained_path": self.pretrained_path,
                "freeze_encoder": self.freeze_encoder,
            }
        )
        return out


__all__ = ["AutoencoderBackbone"]
