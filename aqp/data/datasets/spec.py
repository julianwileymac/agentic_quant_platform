"""``DatasetSpec`` — the serialisable, hash-locked dataset descriptor.

Every :class:`DatasetCatalog` row in Postgres can be reconstructed
into a runtime :class:`BaseDataset` via this spec. The spec is
hashable so a stable ``spec_hash`` lets the discovery browser and the
metadata cache know whether two entries are byte-identical without
loading any payload bytes.

Hash algorithm: SHA-256 over the canonical JSON serialisation of
``{kind, config, medallion_layer, business_metadata, data_contract}``
with sorted keys + no whitespace. Stable across processes and Python
versions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MedallionLayer = Literal["bronze", "silver", "gold"]


class DatasetSpec(BaseModel):
    """Serialisable descriptor for a :class:`BaseDataset` instance."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(..., description="Registered dataset kind, e.g. 'iceberg'.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Kind-specific configuration (paths, identifiers, auth keys).",
    )
    medallion_layer: MedallionLayer | None = Field(
        default=None,
        description="Optional medallion layer (bronze / silver / gold).",
    )
    business_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional business metadata payload (data_owner, semantic_definition, ...).",
    )
    data_contract: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional data contract payload (column-level types / required / range).",
    )

    @field_validator("kind")
    @classmethod
    def _normalise_kind(cls, value: str) -> str:
        cleaned = (value or "").strip().lower()
        if not cleaned:
            raise ValueError("DatasetSpec.kind is required")
        return cleaned

    def to_canonical(self) -> dict[str, Any]:
        """Return a stable, sortable dict for hashing + cache writes."""
        return {
            "kind": self.kind,
            "config": _canonicalise(self.config),
            "medallion_layer": self.medallion_layer,
            "business_metadata": _canonicalise(self.business_metadata),
            "data_contract": _canonicalise(self.data_contract),
        }

    def compute_hash(self) -> str:
        """SHA-256 over the canonical JSON form."""
        payload = json.dumps(
            self.to_canonical(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def with_overrides(self, **overrides: Any) -> DatasetSpec:
        """Return a copy with the given top-level overrides applied."""
        data = self.model_dump()
        data.update(overrides)
        return DatasetSpec(**data)


def _canonicalise(value: Any) -> Any:
    """Recursively sort dict keys so the canonical form is deterministic."""
    if isinstance(value, dict):
        return {k: _canonicalise(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_canonicalise(v) for v in value]
    if isinstance(value, tuple):
        return [_canonicalise(v) for v in value]
    return value


__all__ = ["DatasetSpec", "MedallionLayer"]
