"""Tests for the bundled dataset kinds.

The kinds that need optional extras (parquet / iceberg / partitioned)
are covered by integration tests under :file:`tests/data/`. Here we
only exercise the read-only kinds that don't need extras, plus the
medallion-namespace validation in :class:`IcebergDataset`.
"""
from __future__ import annotations

import pytest

from aqp.data.datasets import DatasetSpec
from aqp.data.datasets.exceptions import DatasetNotMaterialized, DatasetSaveDisabled
from aqp.data.datasets.kinds.external import ExternalDataset
from aqp.data.datasets.kinds.iceberg import IcebergDataset


def test_external_load_raises_not_materialized() -> None:
    spec = DatasetSpec(
        kind="external",
        config={"source_uri": "https://api.example.com/v1/quotes"},
    )
    dataset = ExternalDataset(spec)
    with pytest.raises(DatasetNotMaterialized):
        dataset.load()
    with pytest.raises(DatasetSaveDisabled):
        dataset.save({"foo": "bar"})


def test_external_requires_uri_or_docs() -> None:
    with pytest.raises(ValueError):
        ExternalDataset(DatasetSpec(kind="external", config={}))


def test_iceberg_dataset_validates_identifier() -> None:
    with pytest.raises(ValueError):
        IcebergDataset(DatasetSpec(kind="iceberg", config={"identifier": "no_dot"}))
    with pytest.raises(ValueError):
        IcebergDataset(DatasetSpec(kind="iceberg", config={}))


def test_iceberg_dataset_validates_medallion_alignment() -> None:
    # bronze layer must use 'aqp_bronze_*' prefix
    with pytest.raises(ValueError):
        IcebergDataset(
            DatasetSpec(
                kind="iceberg",
                config={"identifier": "aqp_silver_demo.t"},
                medallion_layer="bronze",
            )
        )
    # matching prefix is accepted
    spec = DatasetSpec(
        kind="iceberg",
        config={"identifier": "aqp_bronze_demo.t"},
        medallion_layer="bronze",
    )
    dataset = IcebergDataset(spec)
    assert dataset.identifier == "aqp_bronze_demo.t"


def test_dataset_describe_includes_kind_and_hash() -> None:
    spec = DatasetSpec(
        kind="external",
        config={"source_uri": "s3://example/path"},
    )
    desc = ExternalDataset(spec).describe()
    assert desc["kind"] == "external"
    assert desc["spec_hash"] == spec.compute_hash()
    assert desc["writable"] is False
