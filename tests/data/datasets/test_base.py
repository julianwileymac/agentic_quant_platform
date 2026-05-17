"""Tests for ``aqp.data.datasets`` — registry + spec hashing.

Covers:

- Subclasses auto-register through the metaclass hook.
- ``DatasetSpec.compute_hash()`` is deterministic + insensitive to dict
  insertion order.
- ``build_dataset(spec)`` materialises the right subclass.
- Unknown kinds raise :class:`DatasetKindUnknown`.
"""
from __future__ import annotations

from typing import Any

import pytest

from aqp.data.datasets import (
    BaseDataset,
    DatasetKindUnknown,
    DatasetSpec,
    build_dataset,
    iter_dataset_kinds,
    register_dataset_kind,
)
from aqp.data.datasets.registry import unregister_dataset_kind


class _AbstractEcho(BaseDataset):
    """Test fixture — round-trips ``payload`` from spec.config['echo']."""

    kind = "_test_echo"

    def _load(self) -> Any:
        return self._spec.config.get("echo")


def test_subclass_auto_registers() -> None:
    assert "_test_echo" in list(iter_dataset_kinds())
    spec = DatasetSpec(kind="_test_echo", config={"echo": "hello"})
    dataset = build_dataset(spec)
    assert isinstance(dataset, _AbstractEcho)
    assert dataset.load() == "hello"


def test_spec_hash_is_stable_across_dict_order() -> None:
    a = DatasetSpec(kind="iceberg", config={"identifier": "ns.t", "limit": 100})
    b = DatasetSpec(kind="iceberg", config={"limit": 100, "identifier": "ns.t"})
    assert a.compute_hash() == b.compute_hash()
    assert a.compute_hash() != DatasetSpec(
        kind="iceberg", config={"identifier": "ns.t", "limit": 50}
    ).compute_hash()


def test_unknown_kind_raises() -> None:
    with pytest.raises(DatasetKindUnknown):
        build_dataset(DatasetSpec(kind="not_real_kind_xyz"))


def test_register_idempotent() -> None:
    # Registering twice with the same class is a no-op.
    register_dataset_kind("_test_echo", _AbstractEcho)
    assert "_test_echo" in list(iter_dataset_kinds())


def test_rebind_refused() -> None:
    class _Other(BaseDataset):
        kind = "_test_rebind_target"

        def _load(self) -> Any:
            return None

    class _Different(BaseDataset):
        kind = "_test_rebind_different"

        def _load(self) -> Any:
            return None

    with pytest.raises(ValueError):
        register_dataset_kind("_test_rebind_target", _Different)

    unregister_dataset_kind("_test_rebind_target")
    unregister_dataset_kind("_test_rebind_different")


def test_kind_normalisation() -> None:
    spec = DatasetSpec(kind="  ICEBERG  ")
    assert spec.kind == "iceberg"


def test_writable_default_true() -> None:
    assert _AbstractEcho.writable is True
