from __future__ import annotations

import pytest

dg = pytest.importorskip("dagster")
pa = pytest.importorskip("pyarrow")

from aqp.dagster.asset_factory import DagsterAssetFactory
from aqp.data.fabric.schema_registry import OHLCVSchema


def test_build_transformation_op_wraps_function() -> None:
    factory = DagsterAssetFactory()

    def _identity(table: pa.Table, params: dict[str, object]) -> pa.Table:
        _ = params
        return table

    op_definition = factory.build_transformation_op(
        _identity,
        input_schema=OHLCVSchema,
        output_schema=OHLCVSchema,
    )

    assert isinstance(op_definition, dg.OpDefinition)
