"""Dataset-kind registry.

Mirrors the shape of :mod:`aqp.core.registry` but is scoped to dataset
kinds so the metadata cache can enumerate kinds without colliding with
strategies / engines / models.

Subclasses of :class:`aqp.data.datasets.base.BaseDataset` self-register
through ``__init_subclass__`` (see :mod:`aqp.data.datasets.base`); the
explicit :func:`register_dataset_kind` decorator is provided for cases
where the subclass lives outside the package and an alias is desired.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from typing import Any, Callable, TypeVar

from aqp.data.datasets.exceptions import DatasetKindUnknown
from aqp.data.datasets.spec import DatasetSpec

_T = TypeVar("_T")

_LOCK = threading.RLock()
_REGISTRY: dict[str, type] = {}


def register_dataset_kind(kind: str, cls: type | None = None) -> Callable[[type], type] | type:
    """Register a :class:`BaseDataset` subclass under ``kind``.

    Idempotent: re-registering the same class under the same kind is a
    no-op. Re-registering under the same kind with a *different* class
    raises :class:`ValueError` to catch accidental shadowing.

    Usable as a decorator (``@register_dataset_kind("iceberg")``) or as
    a direct function call.
    """
    cleaned = str(kind or "").strip().lower()
    if not cleaned:
        raise ValueError("dataset kind cannot be empty")

    def _do_register(target_cls: type) -> type:
        with _LOCK:
            existing = _REGISTRY.get(cleaned)
            if existing is None:
                _REGISTRY[cleaned] = target_cls
                return target_cls
            if existing is target_cls:
                return target_cls
            raise ValueError(
                f"dataset kind {cleaned!r} already registered to "
                f"{existing.__module__}.{existing.__name__}; cannot rebind to "
                f"{target_cls.__module__}.{target_cls.__name__}"
            )

    if cls is None:
        return _do_register  # decorator form
    return _do_register(cls)


def unregister_dataset_kind(kind: str) -> bool:
    """Test helper: drop ``kind`` from the registry."""
    cleaned = str(kind or "").strip().lower()
    with _LOCK:
        return _REGISTRY.pop(cleaned, None) is not None


def get_dataset_kind(kind: str) -> type:
    """Return the class registered under ``kind``."""
    cleaned = str(kind or "").strip().lower()
    with _LOCK:
        cls = _REGISTRY.get(cleaned)
    if cls is None:
        raise DatasetKindUnknown(
            f"dataset kind {cleaned!r} is not registered; known kinds: "
            f"{sorted(_REGISTRY)}"
        )
    return cls


def iter_dataset_kinds() -> Iterator[str]:
    """Iterate kind aliases in deterministic alphabetical order."""
    with _LOCK:
        for kind in sorted(_REGISTRY):
            yield kind


def list_dataset_kinds() -> list[str]:
    return list(iter_dataset_kinds())


def known_dataset_kinds_snapshot() -> Mapping[str, str]:
    """Diagnostic helper: ``{kind: dotted-class-path}``."""
    with _LOCK:
        return {
            kind: f"{cls.__module__}.{cls.__name__}" for kind, cls in _REGISTRY.items()
        }


def build_dataset(spec: DatasetSpec | dict[str, Any]) -> Any:
    """Materialise a :class:`BaseDataset` from a spec (or dict)."""
    if not isinstance(spec, DatasetSpec):
        spec = DatasetSpec(**dict(spec))
    cls = get_dataset_kind(spec.kind)
    return cls(spec)


__all__ = [
    "build_dataset",
    "get_dataset_kind",
    "iter_dataset_kinds",
    "known_dataset_kinds_snapshot",
    "list_dataset_kinds",
    "register_dataset_kind",
    "unregister_dataset_kind",
]
