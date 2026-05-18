"""OpenMetadata-style lineage graph payload models."""
from __future__ import annotations

import logging
from typing import Any, ClassVar, Literal

from pydantic import Field

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase, _urn_validator

logger = logging.getLogger(__name__)


class LineageEdge(AQPOpenMetadataBase):
    """Directed relationship between two metadata entities."""

    aspect_name: ClassVar[str] = "lineageEdge"

    from_entity: str = Field(
        ...,
        description="AQP URN of the upstream entity. Must be a valid AQP URN.",
    )
    to_entity: str = Field(
        ...,
        description="AQP URN of the downstream entity. Must be a valid AQP URN.",
    )
    edge_type: Literal[
        "raw_to_table",
        "table_to_feature",
        "feature_to_model",
        "model_to_signal",
        "signal_to_order",
        "order_to_ledger",
    ] = Field(
        ...,
        description="Canonical edge type describing the transformation relationship.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form edge metadata: actor, run_id, transform details, etc.",
    )

    _validate_from_entity = _urn_validator("from_entity")
    _validate_to_entity = _urn_validator("to_entity")


class EntityLineage(AQPOpenMetadataBase):
    """Lineage snapshot centered around a focal entity URN."""

    entity: str = Field(
        ...,
        description="Focal AQP URN of this lineage graph.",
    )
    upstream_edges: list[LineageEdge] = Field(
        default_factory=list,
        description="Edges pointing INTO the focal entity.",
    )
    downstream_edges: list[LineageEdge] = Field(
        default_factory=list,
        description="Edges pointing OUT of the focal entity.",
    )
    depth: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Traversal depth used to construct this snapshot.",
    )

    _validate_entity = _urn_validator("entity")


__all__ = ["EntityLineage", "LineageEdge"]
