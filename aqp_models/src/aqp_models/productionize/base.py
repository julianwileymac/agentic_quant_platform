"""Shared compiler ABC + registry.

The four compilers (ONNX, TensorRT, TorchScript, quantization) all
implement :meth:`BaseCompiler.compile`. The base class enforces:

* A consistent :class:`CompiledArtifact` return value with SHA-256.
* Best-effort temp-directory cleanup on failure.
* Optional dependency degradation — when the underlying library is
  not installed, ``can_run`` returns ``False`` and the central
  registry's ``get_compiler`` raises a clear error rather than
  exploding inside the route.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CompiledArtifact:
    """Output of any :class:`BaseCompiler.compile` call."""

    path: Path
    format: str
    sha256: str
    size_bytes: int
    compile_kwargs: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "format": self.format,
            "sha256": self.sha256,
            "size_bytes": int(self.size_bytes),
            "compile_kwargs": dict(self.compile_kwargs),
        }


_COMPILERS: dict[str, type["BaseCompiler"]] = {}


def register_compiler(target: str):
    """Class decorator that registers a compiler for ``target``."""

    def wrap(cls: type[BaseCompiler]) -> type[BaseCompiler]:
        if not issubclass(cls, BaseCompiler):
            raise TypeError(f"{cls!r} must subclass BaseCompiler")
        cls.target = target
        _COMPILERS[target] = cls
        # Also tag in the central registry so the UI can enumerate.
        register(cls.__name__, kind="model_compiler", tags=(f"target:{target}",))(cls)
        return cls

    return wrap


def get_compiler(target: str) -> type["BaseCompiler"]:
    if target not in _COMPILERS:
        raise KeyError(
            f"unknown compile target {target!r}; known: {sorted(_COMPILERS)}"
        )
    return _COMPILERS[target]


def list_compilers() -> list[dict[str, Any]]:
    return [
        {
            "target": target,
            "compiler": cls.__name__,
            "available": cls().can_run(),
        }
        for target, cls in sorted(_COMPILERS.items())
    ]


class BaseCompiler(ABC):
    """Abstract compiler ABC."""

    target: ClassVar[str] = ""
    output_format: ClassVar[str] = ""

    def __init__(self, **kwargs: Any) -> None:
        self.compile_kwargs = dict(kwargs)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def compile(
        self,
        model: Any,
        *,
        output_path: str | None = None,
    ) -> CompiledArtifact:
        if not self.can_run():
            raise RuntimeError(
                f"{self.__class__.__name__} unavailable: missing optional dep"
            )
        target_path = (
            Path(output_path)
            if output_path
            else _temp_artifact_path(self.output_format)
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._do_compile(model, target_path)
        except Exception:
            target_path.unlink(missing_ok=True)
            raise

        sha = _sha256_file(target_path)
        size = int(target_path.stat().st_size)
        return CompiledArtifact(
            path=target_path,
            format=self.output_format,
            sha256=sha,
            size_bytes=size,
            compile_kwargs=dict(self.compile_kwargs),
        )

    # ------------------------------------------------------------------
    # Hooks subclasses implement
    # ------------------------------------------------------------------

    @abstractmethod
    def _do_compile(self, model: Any, target_path: Path) -> None:
        """Write the compiled artifact to ``target_path``."""

    @abstractmethod
    def can_run(self) -> bool:
        """Return ``True`` when the optional dep stack is importable."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _temp_artifact_path(extension: str) -> Path:
    tmpdir = Path(tempfile.mkdtemp(prefix="aqp_compile_"))
    return tmpdir / f"artifact.{extension}"


def _unwrap_torch_module(model: Any) -> Any:
    """Resolve an underlying ``torch.nn.Module`` from a qlib wrapper.

    The AQP torch zoo models keep the actual module on ``self.model``.
    HuggingFace pipelines keep it on ``.pipeline_.model``. Direct
    ``nn.Module`` instances pass through. Returns the same object when
    we cannot unwrap further.
    """
    try:
        import torch

        if isinstance(model, torch.nn.Module):
            return model
    except Exception:  # noqa: BLE001
        return model

    inner = getattr(model, "model", None)
    if inner is not None:
        try:
            import torch

            if isinstance(inner, torch.nn.Module):
                return inner
        except Exception:  # noqa: BLE001
            pass

    pipeline = getattr(model, "pipeline_", None)
    if pipeline is not None:
        inner = getattr(pipeline, "model", None)
        if inner is not None:
            return inner

    return model


__all__ = [
    "BaseCompiler",
    "CompiledArtifact",
    "_sha256_file",
    "_unwrap_torch_module",
    "get_compiler",
    "list_compilers",
    "register_compiler",
]
