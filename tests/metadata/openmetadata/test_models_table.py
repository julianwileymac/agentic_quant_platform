"""Tests for OpenMetadata dataset table models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from aqp.metadata.openmetadata import DatasetTable, TableColumn, TableConstraint


def _valid_table_payload() -> dict[str, object]:
    """Return a valid payload for `DatasetTable` tests."""
    return {
        "urn": "urn:aqp:dataset:dev:aqp_silver_alpha_vantage.daily_bars",
        "name": "daily_bars",
        "iceberg_identifier": "aqp_silver_alpha_vantage.daily_bars",
        "medallion_layer": "silver",
        "columns": [
            TableColumn(
                name="close",
                data_type="float64",
                nullable=False,
                description="Closing price.",
                tags=["price"],
            ),
            TableColumn(
                name="volume",
                data_type="int64",
                nullable=False,
                tags=["liquidity"],
            ),
        ],
        "constraints": [
            TableConstraint(
                constraint_type="NOT_NULL",
                columns=["close", "volume"],
            )
        ],
        "description": "Daily OHLCV bars for downstream feature engineering.",
        "business_metadata": {"data_owner": "market-data-team"},
    }


def test_dataset_table_valid_payload() -> None:
    """DatasetTable should parse valid payloads and preserve column metadata."""
    table = DatasetTable(**_valid_table_payload())

    assert table.medallion_layer == "silver"
    assert table.columns[0].name == "close"
    assert table.constraints[0].constraint_type == "NOT_NULL"


def test_dataset_table_rejects_invalid_urn() -> None:
    """Dataset table URNs must use the AQP URN pattern."""
    payload = _valid_table_payload()
    payload["urn"] = "urn:foo:bar"

    with pytest.raises(ValidationError):
        DatasetTable(**payload)


def test_dataset_table_rejects_invalid_medallion_layer() -> None:
    """Medallion layer accepts only bronze/silver/gold."""
    payload = _valid_table_payload()
    payload["medallion_layer"] = "platinum"

    with pytest.raises(ValidationError) as exc_info:
        DatasetTable(**payload)
    assert "medallion_layer" in str(exc_info.value)
