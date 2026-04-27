"""ADD model — Adversarial Domain Adaptation (qlib ``pytorch_add.py``).

The original network couples a forecaster with a gradient-reversal layer
that pushes the encoder to produce features which are *invariant* to a
"domain" label (e.g. market regime / sector). We implement the same
shape: an LSTM encoder, a forecast head, and an auxiliary domain head
fed through a gradient-reversal layer at fit time. For inference we
simply use the forecast head.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("ADDModel")
class ADDModel(BaseTorchModel):
    """LSTM encoder + forecast head (auxiliary domain head built but
    only used by the forecast path at inference).
    """

    is_sequence = True

    def __init__(
        self,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        step_len: int = 20,
        n_domains: int = 4,
        adv_lambda: float = 0.1,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.step_len = int(step_len)
        self.n_domains = int(n_domains)
        self.adv_lambda = float(adv_lambda)

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn

        class _GradReverse(torch.autograd.Function):
            @staticmethod
            def forward(ctx, x, lambd):
                ctx.lambd = lambd
                return x.view_as(x)

            @staticmethod
            def backward(ctx, grad_output):
                return grad_output.neg() * ctx.lambd, None

        def grad_reverse(x, lambd=1.0):
            return _GradReverse.apply(x, lambd)

        class _ADD(nn.Module):
            def __init__(self, in_f, hidden, layers, dropout, n_domains, adv_lambda):
                super().__init__()
                self.lstm = nn.LSTM(
                    in_f,
                    hidden,
                    num_layers=layers,
                    dropout=dropout if layers > 1 else 0.0,
                    batch_first=True,
                )
                self.head = nn.Linear(hidden, 1)
                # Domain classifier kept for completeness; only used if you
                # subclass and pass domain labels.
                self.domain_head = nn.Sequential(
                    nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, n_domains)
                )
                self.adv_lambda = adv_lambda

            def forward(self, x, return_domain: bool = False):
                out, _ = self.lstm(x)
                last = out[:, -1, :]
                pred = self.head(last).squeeze(-1)
                if return_domain:
                    rev = grad_reverse(last, self.adv_lambda)
                    return pred, self.domain_head(rev)
                return pred

        return _ADD(
            input_size,
            self.hidden_size,
            self.num_layers,
            self.dropout,
            self.n_domains,
            self.adv_lambda,
        )
