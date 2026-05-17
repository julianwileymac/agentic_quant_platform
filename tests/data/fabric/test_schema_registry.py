from __future__ import annotations

from datetime import datetime, timezone

import pyarrow as pa
import pytest

from aqp.data.fabric.schema_registry import (
    SCHEMA_REGISTRY,
    CanonicalSchemaBase,
    FeatureSchema,
    FundamentalsSchema,
    InstrumentMetaSchema,
    MacroIndicatorSchema,
    OHLCVSchema,
    SchemaValidationError,
    TickSchema,
)


def test_six_canonical_schemas_registered() -> None:
    for schema_cls in (
        OHLCVSchema,
        MacroIndicatorSchema,
        TickSchema,
        FundamentalsSchema,
        FeatureSchema,
        InstrumentMetaSchema,
    ):
        assert schema_cls.__name__ in SCHEMA_REGISTRY


def test_ohlcv_validate_table_casts_columns() -> None:
    table = pa.table(
        {
            "symbol": pa.array(["AAPL"], type=pa.string()),
            "source_feed_id": pa.array(["source"], type=pa.string()),
            "timestamp": pa.array(
                [datetime(2026, 1, 1, tzinfo=timezone.utc)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "open": pa.array([100.0], type=pa.float64()),
            "high": pa.array([101.0], type=pa.float64()),
            "low": pa.array([99.5], type=pa.float64()),
            "close": pa.array([100.5], type=pa.float32()),
            "volume": pa.array([1000.0], type=pa.float64()),
        }
    )

    validated = OHLCVSchema.validate_table(table)
    assert validated.schema.field("close").type == pa.float64()


def test_ohlcv_validate_table_rejects_missing_field() -> None:
    table = pa.table(
        {
            "symbol": ["AAPL"],
            "source_feed_id": ["source"],
            "timestamp": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.5],
            "close": [100.5],
        }
    )

    with pytest.raises(SchemaValidationError):
        OHLCVSchema.validate_table(table)


def test_evolution_diff_smoke() -> None:
    class _TestSchema(CanonicalSchemaBase):
        PARENT_SCHEMA = OHLCVSchema.CANONICAL_SCHEMA
        CANONICAL_SCHEMA = pa.schema(
            list(OHLCVSchema.CANONICAL_SCHEMA)
            + [pa.field("adjusted_close", pa.float64())]
        )

    diff = _TestSchema.evolution_diff()
    assert "adjusted_close" in diff["added"]
