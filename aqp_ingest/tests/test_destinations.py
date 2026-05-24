"""IcebergBronzeDestination + namespace validation tests."""
from __future__ import annotations

from aqp_ingest_cdk.destinations import (
    IcebergBronzeDestination,
    _slug_to_bronze_ns,
)


def test_slug_to_bronze_ns_normalises_dashes():
    assert (
        _slug_to_bronze_ns("polygon-aggregates")
        == "aqp_bronze_airbyte_polygon_aggregates"
    )
    assert _slug_to_bronze_ns("Polygon_Aggregates") == "aqp_bronze_airbyte_polygon_aggregates"


def test_destination_namespace_property():
    dest = IcebergBronzeDestination(connector_slug="databento-historical")
    assert dest.namespace == "aqp_bronze_airbyte_databento_historical"


def test_write_no_op_on_empty_records():
    dest = IcebergBronzeDestination(connector_slug="alpaca-bars")
    assert dest.write(stream="bars", records=[]) == 0
