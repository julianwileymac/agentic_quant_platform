"""Smoke tests for the file → Iceberg ingestion pipeline.

Uses a synthetic ZIP containing a CSV (CFPB-style) and an NDJSON
(FDA-style) member, points the catalog at a temp warehouse, and
asserts that:

- discovery groups members by family.
- materialize creates Iceberg tables and writes the expected row counts.
- the runner returns a populated :class:`IngestionReport`.

The annotation step is mocked so the test is hermetic and does not
require a live LLM backend.
"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("pyiceberg", reason="Iceberg extra not installed")


def _make_fixture_zip(tmp_path: Path) -> Path:
    """Build a small ZIP containing a CSV + NDJSON sample dataset."""
    zip_path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Two CSV files in the same family ("public_lar") to verify grouping.
        zf.writestr(
            "2022_public_lar.csv",
            "year,county,loan_amount,applicant_age\n"
            "2022,12001,150000,32\n"
            "2022,12003,275000,45\n",
        )
        zf.writestr(
            "2023_public_lar.csv",
            "year,county,loan_amount,applicant_age\n"
            "2023,12001,180000,29\n"
            "2023,12003,310000,41\n"
            "2023,12005,225000,52\n",
        )
        # NDJSON cousin (FDA-style).
        ndjson_lines = [
            json.dumps({"event_id": "E1", "outcome": "ok", "patient": {"age": 30}}),
            json.dumps({"event_id": "E2", "outcome": "fail", "patient": {"age": 55}}),
        ]
        zf.writestr("device-event-0001-of-0001.json", "\n".join(ndjson_lines))
    return zip_path


@pytest.fixture
def iceberg_workspace(tmp_path, monkeypatch):
    """Configure AQP settings to point at a tmp PyIceberg SQL catalog."""
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir(parents=True, exist_ok=True)

    from aqp.config import settings
    from aqp.data import iceberg_catalog as ic

    monkeypatch.setattr(settings, "iceberg_rest_uri", "")
    monkeypatch.setattr(settings, "iceberg_warehouse", warehouse)
    monkeypatch.setattr(settings, "iceberg_namespace_default", "test_aqp")
    monkeypatch.setattr(settings, "iceberg_catalog_name", "aqp_test")
    monkeypatch.setattr(settings, "iceberg_max_rows_per_dataset", 10_000)
    monkeypatch.setattr(settings, "iceberg_max_files_per_dataset", 100)
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_access_key", "")
    monkeypatch.setattr(settings, "s3_secret_key", "")

    ic.reset_catalog_cache()
    yield warehouse
    ic.reset_catalog_cache()


def test_discovery_groups_members_by_family(tmp_path):
    from aqp.data.pipelines.discovery import discover_datasets

    zip_path = _make_fixture_zip(tmp_path)
    datasets = discover_datasets(zip_path)
    families = {d.family for d in datasets if d.family != "__assets__"}
    assert any("lar" in fam for fam in families), families
    assert any("device_event" in fam or "device-event" in fam.replace("_", "-") for fam in families), families


def test_pipeline_smoke_writes_to_iceberg(iceberg_workspace, tmp_path, monkeypatch):
    from aqp.data import iceberg_catalog as ic
    from aqp.data.pipelines import IngestionPipeline
    from aqp.data.pipelines import annotate as annotate_mod

    # Stub out the LLM annotator so the test is hermetic.
    def _fake_annotate(iceberg_identifier, **kwargs):
        return annotate_mod.AnnotationResult(
            identifier=iceberg_identifier,
            description=f"stub description for {iceberg_identifier}",
            tags=["stub", "test"],
            domain="test.dataset",
        )

    monkeypatch.setattr("aqp.data.pipelines.runner.annotate_table", _fake_annotate)

    zip_path = _make_fixture_zip(tmp_path)
    # Disable the LLM Director so the test stays hermetic; the runner
    # will use the deterministic identity-plan fallback instead.
    pipe = IngestionPipeline(director_enabled=False)
    report = pipe.run_path(zip_path, namespace="test_smoke", annotate=True)

    assert report.datasets_discovered >= 2
    assert report.errors == [], report.errors
    table_ids = {t.iceberg_identifier for t in report.tables}
    assert all(tid.startswith("test_smoke.") for tid in table_ids)

    total_rows = sum(t.rows_written for t in report.tables)
    assert total_rows >= 7  # 2 + 3 + 2

    # Sanity check that the Iceberg tables are actually queryable.
    for tid in table_ids:
        arrow = ic.read_arrow(tid, limit=10)
        assert arrow is not None
        assert arrow.num_rows > 0

    # Annotation payload reached the report.
    annotated = [t for t in report.tables if t.annotation]
    assert annotated, "expected at least one annotated table"
    for t in annotated:
        assert t.annotation and "stub description" in (t.annotation.get("description") or "")


def test_register_iceberg_dataset_persists_metadata(in_memory_db, iceberg_workspace, tmp_path):
    """register_iceberg_dataset writes catalog + version rows for non-OHLCV data."""
    from aqp.data.catalog import register_iceberg_dataset
    import pandas as pd

    sample = pd.DataFrame({"event_id": ["A", "B"], "outcome": ["ok", "fail"]})
    result = register_iceberg_dataset(
        iceberg_identifier="test_smoke.example",
        sample_df=sample,
        domain="test.dataset",
        source_uri=str(tmp_path / "fixture.zip"),
        load_mode="managed",
        llm_annotations={"description": "tiny test dataset"},
        column_docs=[
            {"name": "event_id", "description": "Unique id", "pii": False},
            {"name": "outcome", "description": "Test outcome", "pii": False},
        ],
        tags=["test"],
        row_count=2,
        truncated=False,
    )
    assert result.get("dataset_catalog_id")
    assert result.get("dataset_version_id")
