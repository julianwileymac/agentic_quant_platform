from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aqp.data.dbt import DbtExportOptions, DbtExporter, DbtProjectManager
from aqp.data.dbt.artifacts import load_manifest_models, load_model_detail, load_run_results
from aqp.data.engine.registry import get_node_class
from aqp.persistence.models import Base


def test_project_bootstrap_and_safe_file_access(tmp_path) -> None:
    manager = DbtProjectManager(
        project_dir=tmp_path / "project",
        profiles_dir=tmp_path / "profiles",
        duckdb_path=tmp_path / "aqp.duckdb",
        export_dir=tmp_path / "exports",
    )

    result = manager.ensure_project()

    assert (tmp_path / "project" / "dbt_project.yml").exists()
    assert (tmp_path / "profiles" / "profiles.yml").exists()
    assert result["status"]["dbt_project_yml"] is True

    written = manager.write_file("models/custom_model.sql", "select 1 as ok\n")
    assert written["path"] == "models/custom_model.sql"
    assert manager.read_file("models/custom_model.sql")["content"] == "select 1 as ok\n"

    with pytest.raises(ValueError):
        manager.write_file("../escape.sql", "select 1\n")
    with pytest.raises(ValueError):
        manager.write_file("models/bad.py", "print('no')\n")


def test_artifact_parsing(tmp_path) -> None:
    project = tmp_path / "project"
    target = project / "target"
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "nodes": {
                    "model.aqp_dbt.example": {
                        "resource_type": "model",
                        "name": "example",
                        "config": {"materialized": "view"},
                        "tags": ["aqp_generated"],
                        "depends_on": {"nodes": ["source.aqp_exports.dataset_catalogs"]},
                        "columns": {"id": {}, "name": {}},
                    }
                },
                "sources": {
                    "source.aqp_exports.dataset_catalogs": {
                        "resource_type": "source",
                        "name": "dataset_catalogs",
                        "source_name": "aqp_exports",
                        "columns": {"id": {}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (target / "run_results.json").write_text(
        json.dumps(
            {
                "elapsed_time": 1.2,
                "metadata": {"generated_at": "2026-04-28T00:00:00Z"},
                "results": [{"unique_id": "model.aqp_dbt.example", "status": "success"}],
            }
        ),
        encoding="utf-8",
    )

    models = load_manifest_models(project)

    assert {row["unique_id"] for row in models} == {
        "model.aqp_dbt.example",
        "source.aqp_exports.dataset_catalogs",
    }
    assert load_model_detail("model.aqp_dbt.example", project)["name"] == "example"
    assert load_run_results(project)["results"][0]["status"] == "success"


def test_exporter_generates_sources_and_models(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    table = Base.metadata.tables["dataset_catalogs"]
    Base.metadata.create_all(engine, tables=[table])
    Session = sessionmaker(bind=engine, future=True)
    with Session.begin() as session:
        session.execute(
            table.insert().values(
                id="dataset-1",
                name="bars",
                provider="fixture",
                domain="market.bars",
                storage_uri=None,
                schema_json={},
                tags=[],
                meta={},
                iceberg_identifier="fixture.bars",
                load_mode="managed",
                llm_annotations={},
                column_docs=[],
                entity_extraction_status="pending",
            )
        )

    @contextmanager
    def session_ctx() -> Iterator[object]:
        session = Session()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr("aqp.data.dbt.exporter.get_session", session_ctx)
    manager = DbtProjectManager(
        project_dir=tmp_path / "project",
        profiles_dir=tmp_path / "profiles",
        duckdb_path=tmp_path / "aqp.duckdb",
        export_dir=tmp_path / "exports",
    )

    result = DbtExporter(manager).export(
        DbtExportOptions(selected_tables=["dataset_catalogs"], include_dataset_models=True)
    )

    assert "dataset_catalogs" in result.exported_tables
    assert (tmp_path / "exports" / "dataset_catalogs.parquet").exists()
    assert (tmp_path / "project" / "models" / "aqp_generated" / "sources.yml").exists()
    assert (
        tmp_path
        / "project"
        / "models"
        / "aqp_generated"
        / "datasets"
        / "dataset_fixture_bars.sql"
    ).exists()


def test_dbt_build_sink_registered() -> None:
    from aqp.data.fetchers.sinks import DbtBuildSink

    assert get_node_class("sink.dbt_build") is DbtBuildSink
