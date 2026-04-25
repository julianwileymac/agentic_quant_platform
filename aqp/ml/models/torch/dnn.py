"""Dense feed-forward model — ``DNNModel`` (qlib ``DNNModelPytorch``)."""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.models.torch._common import BaseTorchModel, _import_torch


@register("DNNModel")
class DNNModel(BaseTorchModel):
    """Multi-layer perceptron with configurable hidden layers."""

    def __init__(
        self,
        layers: list[int] | None = None,
        dropout: float = 0.0,
        activation: str = "relu",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.layers = list(layers or [256, 64, 16])
        self.dropout = float(dropout)
        self.activation = activation

    def build_module(self, input_size: int):
        torch = _import_torch()
        nn = torch.nn
        act_cls = {
            "relu": nn.ReLU,
            "gelu": nn.GELU,
            "tanh": nn.Tanh,
            "sigmoid": nn.Sigmoid,
        }.get(self.activation.lower(), nn.ReLU)
        modules: list[Any] = []
        prev = input_size
        for h in self.layers:
            modules.append(nn.Linear(prev, h))
            modules.append(act_cls())
            if self.dropout > 0:
                modules.append(nn.Dropout(self.dropout))
            prev = h
        modules.append(nn.Linear(prev, 1))
        return nn.Sequential(*modules)
