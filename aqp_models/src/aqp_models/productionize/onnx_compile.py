"""ONNX export compiler.

Exports any ``torch.nn.Module`` to a single-file ONNX graph. Designed
to be the most-portable target: every downstream runtime (ONNX Runtime,
TensorRT, OpenVINO) can ingest the same artifact.
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


@register_compiler("onnx")
class OnnxCompiler(BaseCompiler):
    """Compile a torch model to an ONNX file."""

    output_format = "onnx"

    def can_run(self) -> bool:
        try:
            import torch  # noqa: F401
            import torch.onnx  # noqa: F401
        except Exception:  # noqa: BLE001
            return False
        return True

    def _do_compile(self, model: Any, target_path: Path) -> None:
        import torch

        module = _unwrap_torch_module(model)
        if not hasattr(module, "forward"):
            raise TypeError(
                "ONNX export requires a torch.nn.Module-like object with"
                " ``forward``."
            )

        opset = int(self.compile_kwargs.get("opset_version", 17))
        input_shape = tuple(
            self.compile_kwargs.get("input_shape") or (1, 32)
        )
        dynamic_axes = self.compile_kwargs.get("dynamic_axes") or {
            "input": {0: "batch"},
            "output": {0: "batch"},
        }

        dummy = torch.zeros(*input_shape, dtype=torch.float32)
        was_training = getattr(module, "training", False)
        module.eval()
        try:
            torch.onnx.export(
                module,
                dummy,
                str(target_path),
                opset_version=opset,
                input_names=["input"],
                output_names=["output"],
                dynamic_axes=dynamic_axes,
            )
        finally:
            if was_training:
                module.train()


__all__ = ["OnnxCompiler"]
