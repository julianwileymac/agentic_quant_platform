"""Quantization compiler — FP32 -> FP16 / INT8 for CPU inference.

Uses ``torch.quantization.quantize_dynamic`` for the INT8 path (most
robust across the AQP torch zoo) and ``model.half()`` for FP16. The
output is a TorchScript file because the quantised module needs to be
serialised independently of its Python source.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aqp_models.productionize.base import (
    BaseCompiler,
    _unwrap_torch_module,
    register_compiler,
)

logger = logging.getLogger(__name__)


@register_compiler("quantize")
class QuantizationCompiler(BaseCompiler):
    """Dynamic quantisation for CPU inference."""

    output_format = "pt"

    def can_run(self) -> bool:
        try:
            import torch  # noqa: F401
        except Exception:  # noqa: BLE001
            return False
        return True

    def _do_compile(self, model: Any, target_path: Path) -> None:
        import torch

        module = _unwrap_torch_module(model)
        precision = str(self.compile_kwargs.get("precision", "int8")).lower()
        input_shape = tuple(self.compile_kwargs.get("input_shape") or (1, 32))

        was_training = getattr(module, "training", False)
        module.eval()
        try:
            if precision == "fp16":
                module = module.half()
                dummy = torch.zeros(*input_shape, dtype=torch.float16)
                scripted = torch.jit.trace(module, dummy)
            else:
                quantised = torch.quantization.quantize_dynamic(
                    module,
                    {torch.nn.Linear},
                    dtype=torch.qint8,
                )
                dummy = torch.zeros(*input_shape, dtype=torch.float32)
                scripted = torch.jit.trace(quantised, dummy)
            scripted.save(str(target_path))
        finally:
            if was_training:
                module.train()


__all__ = ["QuantizationCompiler"]
