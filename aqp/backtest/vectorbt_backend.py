"""Lazy vectorbt backend loading.

Vectorbt Pro is proprietary, so AQP treats it as a runtime dependency instead
of vendoring the source. These helpers centralize imports and error messages so
engines and tools fail with a useful install/license hint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VectorbtBackend:
    name: str
    module: Any
    is_pro: bool = False


class VectorbtDependencyError(ImportError):
    """Raised when the requested vectorbt backend is unavailable."""


def import_vectorbtpro() -> VectorbtBackend:
    """Import vectorbt Pro as an optional runtime dependency."""
    try:
        import vectorbtpro as vbt
    except ImportError as exc:  # pragma: no cover - depends on local license.
        raise VectorbtDependencyError(
            "vectorbt Pro is not installed or not licensed for this runtime. "
            "Install your licensed `vectorbtpro` package in the environment; "
            "AQP does not vendor or redistribute vectorbt Pro source."
        ) from exc
    return VectorbtBackend(name="vectorbt-pro", module=vbt, is_pro=True)


def import_vectorbt_oss() -> VectorbtBackend:
    """Import the open-source vectorbt backend."""
    try:
        import vectorbt as vbt
    except ImportError as exc:  # pragma: no cover - optional extra.
        raise VectorbtDependencyError(
            "vectorbt is not installed. Install with `pip install -e \".[vectorbt]\"` "
            "or choose `engine: event` / `engine: backtesting`."
        ) from exc
    return VectorbtBackend(name="vectorbt", module=vbt, is_pro=False)


def import_vectorbt_backend(
    *,
    prefer_pro: bool = False,
    require_pro: bool = False,
) -> VectorbtBackend:
    """Import a vectorbt backend.

    Parameters
    ----------
    prefer_pro:
        Try vectorbt Pro first, falling back to open-source vectorbt.
    require_pro:
        Require vectorbt Pro and do not fall back.
    """
    if prefer_pro or require_pro:
        try:
            return import_vectorbtpro()
        except VectorbtDependencyError:
            if require_pro:
                raise
    return import_vectorbt_oss()


__all__ = [
    "VectorbtBackend",
    "VectorbtDependencyError",
    "import_vectorbt_backend",
    "import_vectorbt_oss",
    "import_vectorbtpro",
]
