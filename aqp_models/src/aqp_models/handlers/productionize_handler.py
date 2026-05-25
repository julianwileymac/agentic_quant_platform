"""ProductionizeHandler — drive the compilation pipeline.

The handler is a thin dispatcher: given a target compiler kind it
resolves the matching class from :mod:`aqp_models.productionize` and
calls its ``compile`` method. The compiler subsystem owns the actual
work (ONNX export, TensorRT optimisation, TorchScript trace,
quantisation).

Persistence is best-effort: when the platform's ``ml_compiled_artifacts``
table is available the handler writes one row per successful
compilation so the operator UI / agents can audit available compiled
variants for a given base model.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp_models.handlers.base import (
    HandlerContext,
    HandlerResult,
    MLOpsHandler,
)

logger = logging.getLogger(__name__)


class ProductionizeResult(HandlerResult):
    """Marker subclass for the route layer's response model."""


class ProductionizeHandler(MLOpsHandler):
    """Compile a trained model to ONNX / TensorRT / TorchScript."""

    handler_name = "ml.productionize"
    required_scopes = ("data:write",)
    mutates = True

    def run(
        self,
        *,
        ctx: HandlerContext,
        model: Any | None = None,
        target: str | None = None,
        model_version_id: str | None = None,
        compiler_kwargs: dict[str, Any] | None = None,
        output_path: str | None = None,
        **_: Any,
    ) -> HandlerResult:
        if model is None:
            return HandlerResult(ok=False, error="productionize requires ``model``")
        if not target:
            return HandlerResult(
                ok=False,
                error=(
                    "productionize requires ``target`` (one of: onnx, tensorrt, "
                    "torchscript, quantize)"
                ),
            )

        try:
            from aqp_models.productionize import get_compiler
        except Exception as exc:  # noqa: BLE001
            return HandlerResult(
                ok=False,
                error=f"productionize subpackage unavailable: {exc}",
            )

        try:
            compiler_cls = get_compiler(target)
        except KeyError as exc:
            return HandlerResult(ok=False, error=str(exc))

        compiler = compiler_cls(**(compiler_kwargs or {}))

        started = datetime.utcnow()
        try:
            artifact = compiler.compile(model, output_path=output_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("productionize compile failed")
            return HandlerResult(
                ok=False,
                error=f"{compiler_cls.__name__} failed: {exc}",
            )

        elapsed_ms = (datetime.utcnow() - started).total_seconds() * 1000.0

        self._persist_artifact(
            ctx=ctx,
            target=target,
            artifact=artifact,
            model_version_id=model_version_id,
            elapsed_ms=elapsed_ms,
        )

        return ProductionizeResult(
            ok=True,
            data={
                "target": target,
                "artifact_path": str(artifact.path),
                "format": artifact.format,
                "sha256": artifact.sha256,
                "size_bytes": int(artifact.size_bytes),
                "compile_kwargs": dict(artifact.compile_kwargs),
            },
            summary=f"compiled to {target}",
            metadata={
                "target": target,
                "format": artifact.format,
                "elapsed_ms": elapsed_ms,
            },
        )

    # ------------------------------------------------------------------
    # Best-effort persistence
    # ------------------------------------------------------------------

    def _persist_artifact(
        self,
        *,
        ctx: HandlerContext,
        target: str,
        artifact: Any,
        model_version_id: str | None,
        elapsed_ms: float,
    ) -> None:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_mlops import MlCompiledArtifact

            with get_session() as session:
                row = MlCompiledArtifact(
                    base_model_version_id=model_version_id,
                    target=target,
                    artifact_format=artifact.format,
                    artifact_path=str(artifact.path),
                    artifact_sha256=artifact.sha256,
                    size_bytes=int(artifact.size_bytes),
                    compile_kwargs=dict(artifact.compile_kwargs),
                    elapsed_ms=float(elapsed_ms),
                    workspace_id=ctx.workspace_id,
                    project_id=ctx.project_id,
                    owner_user_id=(
                        ctx.actor if ctx.actor_kind == "user" else None
                    ),
                )
                session.add(row)
        except Exception:  # noqa: BLE001
            logger.debug("productionize persistence failed", exc_info=True)


__all__ = ["ProductionizeHandler", "ProductionizeResult"]
