"""Tests for metadata schema exporter."""
from __future__ import annotations

import json

import pytest

from aqp.metadata.schema_export import SchemaExporter, cli


def test_discover_models() -> None:
    """Exporter should discover expected OpenMetadata Pydantic model classes."""
    exporter = SchemaExporter()
    models = exporter.discover_models()
    discovered = {model.__name__ for model in models}

    expected = {
        "MlFeature",
        "FeatureSource",
        "MlHyperParameter",
        "MlModel",
        "MlTestResult",
        "Pipeline",
        "PipelineTask",
        "DatasetTable",
        "TableColumn",
        "TableConstraint",
        "LineageEdge",
        "EntityLineage",
        "GlossaryTerm",
        "Document",
    }
    assert len(models) >= 11
    assert expected.issubset(discovered)


def test_export_all_writes_files(tmp_path) -> None:
    """Exporter should create schema files for all configured formats."""
    exporter = SchemaExporter(output_root=tmp_path)
    result = exporter.export_all()

    assert len(result["json"]) >= 6
    assert len(result["avro"]) >= 6
    assert len(result["pdl"]) >= 6


def test_avro_schemas_parse_with_fastavro(tmp_path) -> None:
    """Generated AVRO schemas should parse with fastavro."""
    fastavro = pytest.importorskip("fastavro")
    exporter = SchemaExporter(output_root=tmp_path)
    result = exporter.export_all()

    for schema_path in result["avro"]:
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
        fastavro.parse_schema(payload)


def test_json_schemas_have_required_extras(tmp_path) -> None:
    """JSON Schemas should include draft declaration and AQP extras when applicable."""
    exporter = SchemaExporter(output_root=tmp_path)
    models = exporter.discover_models()

    for model in models:
        schema_path = exporter.export_json_schema(model)
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        entity_type = getattr(model, "entity_type", None)
        if entity_type:
            assert payload["x-aqp-entity-type"] == entity_type


def test_pdl_files_contain_namespace_and_record(tmp_path) -> None:
    """Generated PDL files should include canonical namespace and root record declaration."""
    exporter = SchemaExporter(output_root=tmp_path)
    result = exporter.export_all()

    for pdl_path in result["pdl"]:
        content = pdl_path.read_text(encoding="utf-8")
        assert "namespace com.aqp.models.metadata" in content
        assert f"record {pdl_path.stem} {{" in content


def test_cli_all_format(tmp_path, capsys) -> None:
    """CLI all-format mode should return success and write output files."""
    exit_code = cli(["--format", "all", "--output-root", str(tmp_path), "--quiet"])
    assert exit_code == 0

    assert (tmp_path / "schemas" / "json").exists()
    assert (tmp_path / "schemas" / "avro").exists()
    assert (tmp_path / "schemas" / "pdl").exists()
    assert any((tmp_path / "schemas" / "json").glob("*.schema.json"))
    assert any((tmp_path / "schemas" / "avro").glob("*.avsc"))
    assert any((tmp_path / "schemas" / "pdl").glob("*.pdl"))
    _ = capsys.readouterr()
