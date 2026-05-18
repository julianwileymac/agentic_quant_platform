"""Tests for OpenMetadata lineage models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from aqp.metadata.openmetadata import EntityLineage, LineageEdge


def _valid_edge() -> LineageEdge:
    """Return a canonical valid lineage edge."""
    return LineageEdge(
        from_entity="urn:aqp:dataset:dev:aqp_bronze_alpha.raw_prices",
        to_entity="urn:aqp:dataset:dev:aqp_silver_alpha.daily_bars",
        edge_type="raw_to_table",
        metadata={"run_id": "run-123"},
    )


def test_lineage_models_accept_valid_payloads() -> None:
    """Lineage edge and graph payloads should parse when URNs are valid."""
    edge = _valid_edge()
    lineage = EntityLineage(
        entity="urn:aqp:dataset:dev:aqp_silver_alpha.daily_bars",
        upstream_edges=[edge],
        downstream_edges=[],
        depth=2,
    )

    assert lineage.entity == "urn:aqp:dataset:dev:aqp_silver_alpha.daily_bars"
    assert lineage.upstream_edges[0].edge_type == "raw_to_table"


def test_lineage_edge_rejects_invalid_upstream_or_downstream_urn() -> None:
    """Both lineage edge URN endpoints must pass AQP URN validation."""
    with pytest.raises(ValidationError):
        LineageEdge(
            from_entity="urn:foo:bar",
            to_entity="urn:aqp:dataset:dev:aqp_silver_alpha.daily_bars",
            edge_type="raw_to_table",
        )

    with pytest.raises(ValidationError):
        LineageEdge(
            from_entity="urn:aqp:dataset:dev:aqp_bronze_alpha.raw_prices",
            to_entity="urn:foo:bar",
            edge_type="raw_to_table",
        )


def test_entity_lineage_rejects_depth_over_limit() -> None:
    """Depth bounds should reject traversals larger than the configured max."""
    with pytest.raises(ValidationError):
        EntityLineage(
            entity="urn:aqp:dataset:dev:aqp_silver_alpha.daily_bars",
            depth=11,
        )
