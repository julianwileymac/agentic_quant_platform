"""Compilation pipeline for productionising trained models.

Each compiler is a class registered via the central
:func:`aqp.core.registry.register` decorator under
``kind="model_compiler"`` so the ``data.ml.compile_artifact`` MCP tool
and the FastAPI ``/ml/models/{id}/productionize`` endpoint can browse
available targets without a hard-coded list.

Available compilers:

* :class:`OnnxCompiler` — ONNX export for any torch ``nn.Module``.
* :class:`TensorRTCompiler` — ONNX -> TensorRT engine (skipped at
  runtime when the optional dep is missing).
* :class:`TorchScriptCompiler` — ``torch.jit.trace`` / ``torch.jit.script``
  fallback.
* :class:`QuantizationCompiler` — FP32 -> FP16 / INT8 dynamic
  quantisation for CPU inference.

All compilers return a :class:`CompiledArtifact` dataclass with
``path`` / ``format`` / ``sha256`` / ``compile_kwargs`` /
``size_bytes`` so :class:`aqp_models.handlers.ProductionizeHandler`
can persist the row uniformly.
"""
from __future__ import annotations

from aqp_models.productionize.base import (
    BaseCompiler,
    CompiledArtifact,
    get_compiler,
    list_compilers,
    register_compiler,
)
from aqp_models.productionize.onnx_compile import OnnxCompiler
from aqp_models.productionize.quantization import QuantizationCompiler
from aqp_models.productionize.tensorrt_compile import TensorRTCompiler
from aqp_models.productionize.torchscript_compile import TorchScriptCompiler

__all__ = [
    "BaseCompiler",
    "CompiledArtifact",
    "OnnxCompiler",
    "QuantizationCompiler",
    "TensorRTCompiler",
    "TorchScriptCompiler",
    "get_compiler",
    "list_compilers",
    "register_compiler",
]
