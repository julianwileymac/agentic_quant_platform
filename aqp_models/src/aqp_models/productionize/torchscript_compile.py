"""TorchScript compiler.

Uses ``torch.jit.trace`` by default; ``torch.jit.script`` is opted into
via ``compile_kwargs={"mode": "script"}`` when the model is
TorchScript-compatible. Trace remains the default because it works
for the AQP torch zoo without per-model annotations.
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


@register_compiler("torchscript")
class TorchScriptCompiler(BaseCompiler):
    """Compile a torch model to a ``.pt`` TorchScript artifact."""

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
        mode = str(self.compile_kwargs.get("mode", "trace")).lower()
        input_shape = tuple(self.compile_kwargs.get("input_shape") or (1, 32))

        was_training = getattr(module, "training", False)
        module.eval()
        try:
            if mode == "script":
                scripted = torch.jit.script(module)
            else:
                dummy = torch.zeros(*input_shape, dtype=torch.float32)
                scripted = torch.jit.trace(module, dummy)
            scripted.save(str(target_path))
        finally:
            if was_training:
                module.train()


__all__ = ["TorchScriptCompiler"]
