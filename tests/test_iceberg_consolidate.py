"""Smoke tests for :func:`aqp.data.iceberg_consolidate.consolidate_group`.

Uses a temporary PyIceberg sqlite catalog so the test is hermetic. The
``pyiceberg`` extra is required; we skip otherwise.
"""
from __future__ import annotations

import importlib

import pytest

pyiceberg = pytest.importorskip("pyiceberg")
pa = pytest.importorskip("pyarrow")


@pytest.fixture
def fresh_catalog(tmp_path, monkeypatch):
    """Point ``aqp.config.settings`` at a fresh on-disk catalog."""
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


def _make_table(catalog_module, identifier, rows):
    arrow = pa.table(rows)
    catalog_module.create_or_replace_table(identifier, arrow.schema)
    return catalog_module.append_arrow(identifier, arrow, create_if_missing=False)


def test_dry_run_validates_compatible_schemas(fresh_catalog):
    fresh_catalog.ensure_namespace("aqp")
    _make_table(
        fresh_catalog,
        "aqp.bars_part_1",
        {"timestamp": [pa.scalar("2024-01-01")], "vt_symbol": ["AAA"], "close": [1.0]},
    )
    _make_table(
        fresh_catalog,
        "aqp.bars_part_2",
        {"timestamp": [pa.scalar("2024-01-02")], "vt_symbol": ["AAA"], "close": [2.0]},
    )

    from aqp.data.iceberg_consolidate import consolidate_group

    report = consolidate_group(
        group_name="aqp.bars_merged",
        members=["aqp.bars_part_1", "aqp.bars_part_2"],
        dry_run=True,
        drop_members=False,
    )
    assert report.error is None
    assert report.schema_compatible is True
    assert report.total_rows == 2
    assert report.target_created is False
    # Members untouched.
    assert fresh_catalog.load_table("aqp.bars_part_1") is not None


def test_wet_run_creates_target_and_drops_members(fresh_catalog):
    fresh_catalog.ensure_namespace("aqp")
    _make_table(
        fresh_catalog,
        "aqp.x_part_1",
        {"a": [1, 2], "b": ["x", "y"]},
    )
    _make_table(
        fresh_catalog,
        "aqp.x_part_2",
        {"a": [3], "b": ["z"]},
    )

    from aqp.data.iceberg_consolidate import consolidate_group

    report = consolidate_group(
        group_name="aqp.x_merged",
        members=["aqp.x_part_1", "aqp.x_part_2"],
        dry_run=False,
        drop_members=True,
    )
    assert report.error is None, report.error
    assert report.schema_compatible is True
    assert report.target_created is True
    assert report.total_rows == 3
    assert report.target_rows_after == 3
    assert fresh_catalog.load_table("aqp.x_merged") is not None
    assert fresh_catalog.load_table("aqp.x_part_1") is None
    assert fresh_catalog.load_table("aqp.x_part_2") is None


def test_rejects_too_few_members(fresh_catalog):
    from aqp.data.iceberg_consolidate import consolidate_group

    report = consolidate_group(
        group_name="aqp.unused",
        members=["aqp.only_one"],
        dry_run=True,
        drop_members=False,
    )
    assert report.error is not None
    assert "at least 2" in report.error
