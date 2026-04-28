"""Partition-spec compilation for :mod:`aqp.data.iceberg_catalog` (PyIceberg 0.11+)."""
from __future__ import annotations

import importlib

import pytest

pyiceberg = pytest.importorskip("pyiceberg")
pa = pytest.importorskip("pyarrow")


@pytest.fixture
def fresh_catalog(tmp_path, monkeypatch):
    from aqp.config import settings as _settings
    from aqp.data import iceberg_catalog

    monkeypatch.setattr(_settings, "iceberg_warehouse", tmp_path, raising=False)
    monkeypatch.setattr(_settings, "iceberg_rest_uri", "", raising=False)
    monkeypatch.setattr(_settings, "iceberg_catalog_name", "aqp", raising=False)
    monkeypatch.setattr(_settings, "iceberg_namespace_default", "aqp", raising=False)
    importlib.reload(iceberg_catalog)
    iceberg_catalog.reset_catalog_cache()
    yield iceberg_catalog
    iceberg_catalog.reset_catalog_cache()


def test_create_partitioned_table_dict_spec_no_field_id_error(fresh_catalog) -> None:
    """Dict partition specs must not call pyarrow_to_schema without name mapping."""
    fresh_catalog.ensure_namespace("aqp")
    arrow_schema = pa.schema(
        [
            pa.field("vt_symbol", pa.string()),
            pa.field("timestamp", pa.timestamp("us")),
            pa.field("open", pa.float64()),
        ]
    )
    spec = [
        {"source_column": "vt_symbol", "transform": "bucket[8]", "name": "sym_bucket"},
        {"source_column": "timestamp", "transform": "month", "name": "ts_month"},
    ]
    tbl = fresh_catalog.create_or_replace_table(
        "aqp.av_partition_smoke",
        arrow_schema,
        partition_spec=spec,
    )
    assert tbl is not None
    assert len(tbl.metadata.schema().fields) == 3
    assert len(tbl.spec().fields) == 2
