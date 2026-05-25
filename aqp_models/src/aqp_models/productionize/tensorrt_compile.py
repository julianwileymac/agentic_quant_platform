"""TensorRT compiler.

Two-step pipeline: ONNX export via :class:`OnnxCompiler`, then a
TensorRT engine build via ``tensorrt`` and ``torch_tensorrt`` when
available. TensorRT is GPU-only and Linux-only — :meth:`can_run`
returns ``False`` everywhere else so the compiler registry can offer
the option without breaking the unit tests / CI.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aqp_models.productionize.base import (
    BaseCompiler,
    register_compiler,
)
from aqp_models.productionize.onnx_compile import OnnxCompiler

logger = logging.getLogger(__name__)


@register_compiler("tensorrt")
class TensorRTCompiler(BaseCompiler):
    """ONNX -> TensorRT engine builder."""

    output_format = "engine"

    def can_run(self) -> bool:
        try:
            import tensorrt  # type: ignore[import-not-found]  # noqa: F401
        except Exception:  # noqa: BLE001
            return False
        try:
            import torch  # noqa: F401

            # GPU-only — the engine builder calls into CUDA.
            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            return False

    def _do_compile(self, model: Any, target_path: Path) -> None:
        # Step 1: lower to ONNX in a temp dir.
        onnx_compiler = OnnxCompiler(**self.compile_kwargs)
        intermediate = target_path.with_suffix(".onnx")
        onnx_compiler._do_compile(model, intermediate)

        # Step 2: build the TensorRT engine.
        import tensorrt as trt  # type: ignore[import-not-found]

        precision = str(self.compile_kwargs.get("precision", "fp16")).lower()
        workspace_mb = int(self.compile_kwargs.get("workspace_mb", 1024))

        logger_trt = trt.Logger(trt.Logger.WARNING)
        builder = trt.Builder(logger_trt)
        network = builder.create_network(
            1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
        )
        parser = trt.OnnxParser(network, logger_trt)
        with intermediate.open("rb") as fh:
            parsed = parser.parse(fh.read())
        if not parsed:
            errors = "\n".join(parser.get_error(i).desc() for i in range(parser.num_errors))
            raise RuntimeError(f"TensorRT ONNX parser rejected the model:\n{errors}")

        config = builder.create_builder_config()
        config.max_workspace_size = int(workspace_mb) * (1 << 20)
        if precision == "fp16":
            config.set_flag(trt.BuilderFlag.FP16)
        if precision == "int8":
            config.set_flag(trt.BuilderFlag.INT8)

        engine = builder.build_serialized_network(network, config)
        if engine is None:
            raise RuntimeError("TensorRT engine build returned None")
        target_path.write_bytes(bytes(engine))
        intermediate.unlink(missing_ok=True)


__all__ = ["TensorRTCompiler"]
