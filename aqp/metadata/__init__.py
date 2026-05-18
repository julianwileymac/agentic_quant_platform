"""Consolidated DataHub-style aspect metadata store."""
from __future__ import annotations

import importlib

from aqp.metadata.exceptions import ImmutableAspectError, MetadataValidationError
from aqp.metadata.urn import make_urn, parse_urn, to_datahub_urn

__all__ = [
    "EntityAspect",
    "ImmutableAspectError",
    "MetadataEntity",
    "MetadataValidationError",
    "make_urn",
    "parse_urn",
    "to_datahub_urn",
    "write_aspect",
]


def __getattr__(name: str):
    if name == "write_aspect":
        importlib.import_module("aqp.metadata.projections")
        from aqp.metadata.writer import write_aspect

        return write_aspect
    if name in {"MetadataEntity", "EntityAspect"}:
        from aqp.persistence.models_aspects import EntityAspect, MetadataEntity

        return {"MetadataEntity": MetadataEntity, "EntityAspect": EntityAspect}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

