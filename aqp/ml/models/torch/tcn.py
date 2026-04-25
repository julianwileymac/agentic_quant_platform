"""Temporal Convolutional Network — qlib ``TCN``."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("TCNModel")
class TCNModel(BaseTorchModel):
    """Simple 1D-causal TCN block stack over windowed sequences."""

    is_sequence = True

    def __init__(
        self,
        num_channels: list[int] | None = None,
        kernel_size: int = 3,
        dropout: float = 0.1,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.num_channels = list(num_channels or [32, 64, 128])
        self.kernel_size = int(kernel_size)
        self.dropout = float(dropout)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _CausalBlock(nn.Module):
            def __init__(self, in_ch, out_ch, k, dilation, dropout):
                super().__init__()
                self.padding = (k - 1) * dilation
                self.conv1 = nn.Conv1d(in_ch, out_ch, k, padding=self.padding, dilation=dilation)
                self.conv2 = nn.Conv1d(out_ch, out_ch, k, padding=self.padding, dilation=dilation)
                self.drop = nn.Dropout(dropout)
                self.res = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()

            def forward(self, x):
                out = torch.relu(self.conv1(x)[..., : x.size(-1)])
                out = self.drop(torch.relu(self.conv2(out)[..., : x.size(-1)]))
                return out + self.res(x)

        class _TCN(nn.Module):
            def __init__(self, in_f, chs, k, dropout):
                super().__init__()
                layers = []
                prev = in_f
                for i, c in enumerate(chs):
                    layers.append(_CausalBlock(prev, c, k, dilation=2**i, dropout=dropout))
                    prev = c
                self.net = nn.Sequential(*layers)
                self.head = nn.Linear(prev, 1)

            def forward(self, x):
                # x: (B, T, F) -> (B, F, T)
                x = x.transpose(1, 2)
                h = self.net(x)
                return self.head(h[:, :, -1]).squeeze(-1)

        return _TCN(input_size, self.num_channels, self.kernel_size, self.dropout)
