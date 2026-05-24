"""Validate the Phase 1 + Phase 2 namespace conventions."""
from __future__ import annotations


def test_airbyte_bronze_namespace_convention():
    from aqp_ingest_cdk.destinations import _slug_to_bronze_ns

    assert _slug_to_bronze_ns("polygon").startswith("aqp_bronze_airbyte_")
    assert _slug_to_bronze_ns("Databento-Historical") == "aqp_bronze_airbyte_databento_historical"
