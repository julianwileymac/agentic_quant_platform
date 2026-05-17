from __future__ import annotations

import importlib.util
from datetime import UTC, datetime

import pyarrow as pa
import pytest

from aqp.dagster.asset_factory import DagsterAssetFactory
from aqp.data.fabric.schema_registry import OHLCVSchema, SchemaValidationError


def test_build_transformation_op_validates_schemas() -> None:
    if importlib.util.find_spec("dagster") is None:
        pytest.skip("dagster not installed")

    factory = DagsterAssetFactory()

    def _noop(table: pa.Table) -> pa.Table:
        return table

    op_def = factory.build_transformation_op(
        _noop,
        input_schema=OHLCVSchema,
        output_schema=OHLCVSchema,
        op_name="noop_transform",
    )
    compute_fn = (
        op_def.compute_fn.decorated_fn
        if hasattr(op_def.compute_fn, "decorated_fn")
        else op_def.compute_fn
    )

    valid = pa.table(
        {
            "symbol": ["AAPL"],
            "source_feed_id": ["source-1"],
            "timestamp": pa.array([datetime(2024, 1, 1, tzinfo=UTC)], type=pa.timestamp("us", tz="UTC")),
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [100.0],
        }
    )
    result = compute_fn(valid)
    assert isinstance(result, pa.Table)
    assert result.schema == OHLCVSchema.CANONICAL_SCHEMA

    invalid = pa.table(
        {
            "symbol": ["AAPL"],
            "source_feed_id": ["source-1"],
            "timestamp": pa.array([datetime(2024, 1, 1, tzinfo=UTC)], type=pa.timestamp("us", tz="UTC")),
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
        }
    )
    with pytest.raises(SchemaValidationError):
        compute_fn(invalid)
