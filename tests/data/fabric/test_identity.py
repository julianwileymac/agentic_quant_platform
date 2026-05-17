from __future__ import annotations

import uuid

import pytest

from aqp.data.fabric.identity import (
    FABRIC_REGISTRY,
    FabricContractError,
    FabricIdentity,
    VersionVector,
    mutating,
)


def _is_hex_digest(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value)


def test_fabric_object_meta_registers_class() -> None:
    class _RegisteredIdentity(FabricIdentity):
        def __init__(self, value: int) -> None:
            self.value = value

    key = f"{_RegisteredIdentity.__module__}.{_RegisteredIdentity.__qualname__}"
    assert key in FABRIC_REGISTRY


def test_fabric_identity_seals_uuid_and_hash() -> None:
    class _SealedIdentity(FabricIdentity):
        def __init__(self, value: int) -> None:
            self.value = value

    obj = _SealedIdentity(7)
    assert isinstance(obj.fabric_uuid, uuid.UUID)
    assert _is_hex_digest(obj.content_hash)
    assert obj.version_vector.get(_SealedIdentity.__qualname__) == 0


def test_fabric_hash_changes_after_mutating_method() -> None:
    class _MutatingIdentity(FabricIdentity):
        def __init__(self, value: int) -> None:
            self.value = value

        @mutating
        def set_value(self, value: int) -> None:
            self.value = value

    obj = _MutatingIdentity(1)
    before = obj.content_hash
    obj.set_value(2)
    after = obj.content_hash

    assert before != after
    assert obj.version_vector.get(_MutatingIdentity.__qualname__) == 1
    assert len(obj.lineage_refs) == 1
    assert obj.lineage_refs[-1].transform_kind == "self.mutation"


def test_canonical_dict_is_deterministic() -> None:
    class _CanonicalIdentity(FabricIdentity):
        _fabric_excluded_fields = FabricIdentity._fabric_excluded_fields + ("_transient",)

        def __init__(self, value: int, tags: set[str]) -> None:
            self.value = value
            self.tags = tags
            self._transient = "ignored"

    first = _CanonicalIdentity(42, {"b", "a"})
    second = _CanonicalIdentity(42, {"a", "b"})

    assert first.to_canonical_dict() == first.to_canonical_dict()
    assert first.to_canonical_dict() == second.to_canonical_dict()


def test_compute_dict_hash_matches_compute_hash() -> None:
    class _HashIdentity(FabricIdentity):
        def __init__(self, value: int, payload: dict[str, int]) -> None:
            self.value = value
            self.payload = payload

    obj = _HashIdentity(4, {"x": 1, "y": 2})
    assert obj.compute_hash() == obj.compute_dict_hash(obj.to_canonical_dict())


def test_version_vector_partial_order() -> None:
    left = VersionVector({"loader": 1, "catalog": 2})
    right = VersionVector({"loader": 3, "other": 1})

    merged = left.merge(right)
    assert merged.to_dict() == {"catalog": 2, "loader": 3, "other": 1}
    assert merged.dominates(left)
    assert not left.dominates(right)

    incremented = left.incremented("loader")
    assert incremented.get("loader") == 2
    assert left.get("loader") == 1


def test_fabric_contract_error() -> None:
    with pytest.raises(FabricContractError):

        class _BrokenIdentity(FabricIdentity):
            _abstract_methods = ("fetch_batch",)

            def __init__(self) -> None:
                self.value = 0
