"""``BaseDataset`` ABC and metaclass-driven registration.

Subclasses declare a class attribute ``kind: ClassVar[str]`` and
implement ``_load`` / ``_save`` / ``_describe`` / ``exists``. The
``__init_subclass__`` hook auto-registers them under their ``kind`` so
declaring a new kind is just::

    class MyDataset(BaseDataset):
        kind = "my_kind"
        def _load(self): ...

The base class is deliberately small — the heavy IO lives inside each
kind under :mod:`aqp.data.datasets.kinds`.
"""
from __future__ import annotations

import abc
from typing import Any, ClassVar

from aqp.data.datasets.exceptions import DatasetSaveDisabled
from aqp.data.datasets.registry import register_dataset_kind
from aqp.data.datasets.spec import DatasetSpec


class BaseDataset(abc.ABC):
    """Kedro-style read/write contract for a single catalog entry."""

    #: Registered alias. Subclasses MUST override (empty / ``"_abstract"``
    #: skips registration). Lowercase, snake-case, no spaces.
    kind: ClassVar[str] = "_abstract"

    #: Whether ``save`` is permitted. SQL queries / external API entries
    #: typically set this to ``False`` so accidental writes fail fast.
    writable: ClassVar[bool] = True

    def __init__(self, spec: DatasetSpec | dict[str, Any]) -> None:
        if not isinstance(spec, DatasetSpec):
            spec = DatasetSpec(**dict(spec))
        if spec.kind != type(self).kind:
            raise ValueError(
                f"DatasetSpec.kind={spec.kind!r} does not match class kind "
                f"{type(self).kind!r}"
            )
        self._spec = spec
        self._validate_spec()

    # ---------------------------------------------------------- registration
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        kind = getattr(cls, "kind", "_abstract")
        if kind and kind != "_abstract" and not getattr(cls, "_abstract", False):
            register_dataset_kind(kind, cls)

    # ---------------------------------------------------------- public API
    @property
    def spec(self) -> DatasetSpec:
        return self._spec

    @property
    def config(self) -> dict[str, Any]:
        return dict(self._spec.config)

    @property
    def medallion_layer(self) -> str | None:
        return self._spec.medallion_layer

    @property
    def spec_hash(self) -> str:
        return self._spec.compute_hash()

    def load(self) -> Any:
        return self._load()

    def save(self, payload: Any) -> Any:
        if not type(self).writable:
            raise DatasetSaveDisabled(
                f"dataset kind {type(self).kind!r} is read-only; save is disabled"
            )
        return self._save(payload)

    def describe(self) -> dict[str, Any]:
        return {
            "kind": type(self).kind,
            "writable": type(self).writable,
            "spec_hash": self.spec_hash,
            "medallion_layer": self.medallion_layer,
            **self._describe(),
        }

    def exists(self) -> bool:
        return self._exists()

    def release(self) -> None:
        """Optional teardown hook (close files, drop connections)."""
        return None

    # ---------------------------------------------------------- to override
    def _validate_spec(self) -> None:
        """Subclass hook to validate ``self._spec.config`` shape."""
        return None

    @abc.abstractmethod
    def _load(self) -> Any:
        """Load the dataset payload."""

    def _save(self, payload: Any) -> Any:  # pragma: no cover — default no-op
        raise DatasetSaveDisabled(
            f"dataset kind {type(self).kind!r} did not implement _save"
        )

    def _describe(self) -> dict[str, Any]:
        """Return kind-specific descriptors (paths, sizes, schemas)."""
        return {"config": dict(self._spec.config)}

    def _exists(self) -> bool:
        return False


__all__ = ["BaseDataset"]
