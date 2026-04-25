"""Generic PyTorch adapter — point at any ``nn.Module`` class via ``module_path``.

Use this when you have a hand-written model and just want AQP's Model
contract + training loop around it, mirroring qlib's ``GeneralPTNN``.
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register, resolve
from aqp.ml.models.torch._common import BaseTorchModel


@register("GeneralPTNN")
class GeneralPTNN(BaseTorchModel):
    """Build a user-supplied ``nn.Module`` and run it through our training loop."""

    def __init__(
        self,
        model_class: str,
        model_module: str | None = None,
        model_kwargs: dict[str, Any] | None = None,
        is_sequence: bool = False,
        step_len: int = 20,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.model_class = model_class
        self.model_module = model_module
        self.model_kwargs = dict(model_kwargs or {})
        self.is_sequence = bool(is_sequence)
        self.step_len = int(step_len)

    def build_module(self, input_size: int):
        cls = resolve(self.model_class, self.model_module)
        kwargs = dict(self.model_kwargs)
        kwargs.setdefault("input_size", input_size)
        return cls(**kwargs)
