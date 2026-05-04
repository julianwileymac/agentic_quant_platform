"""Tests for the dataset-loading agent tools.

Each tool returns a JSON-encoded string so the agent (CrewAI / our
runtime stub) can pass it through ``router_complete``. The tools must
never raise — failures are encoded in the JSON body.
"""
from __future__ import annotations

import json
from pathlib import Path


def test_inspect_path_returns_directory_listing(tmp_path: Path) -> None:
    from aqp.agents.tools.data_tools import InspectPathTool

    (tmp_path / "a.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "b.parquet").write_text("", encoding="utf-8")
    out = json.loads(InspectPathTool()._run(str(tmp_path), max_entries=10))
    assert out["kind"] == "directory"
    assert out["total_entries"] == 2
    assert out["suffixes"][".csv"] == 1


def test_inspect_path_handles_missing_path() -> None:
    from aqp.agents.tools.data_tools import InspectPathTool

    out = json.loads(InspectPathTool()._run("/no/such/path"))
    assert "error" in out


def test_lookup_dataset_preset_filter() -> None:
    from aqp.agents.tools.data_tools import LookupDatasetPresetTool

    out = json.loads(LookupDatasetPresetTool()._run("etf"))
    assert any("etf" in (r.get("name") or "").lower() or "etf" in (r.get("description") or "").lower() for r in out["results"])


def test_propose_pipeline_manifest_shape() -> None:
    from aqp.agents.tools.data_tools import ProposePipelineManifestTool

    raw = ProposePipelineManifestTool()._run(
        name="test",
        namespace="aqp",
        source_kind="rest",
        target_table="bars",
        sink_kind="iceberg",
    )
    data = json.loads(raw)
    assert data["name"] == "test"
    assert data["source"]["name"].startswith("source.")
    assert data["sink"]["name"].startswith("sink.")
    assert data["sink"]["kwargs"]["namespace"] == "aqp"


def test_propose_setup_wizard_returns_step_list() -> None:
    from aqp.agents.tools.data_tools import ProposeSetupWizardTool

    raw = ProposeSetupWizardTool()._run("alpha_vantage")
    data = json.loads(raw)
    assert data["source_key"] == "alpha_vantage"
    assert any(step["id"] == "credentials" for step in data["steps"])


def test_summarise_airbyte_catalog_returns_connectors() -> None:
    from aqp.agents.tools.data_tools import SummariseAirbyteCatalogTool

    raw = SummariseAirbyteCatalogTool()._run()
    data = json.loads(raw)
    assert "connectors" in data
    assert isinstance(data["connectors"], list)


def test_dataset_loading_assistant_spec_is_loadable() -> None:
    """The agent spec YAML must parse and register required tools."""
    import yaml

    spec_path = (
        Path(__file__).resolve().parents[2]
        / "configs"
        / "agents"
        / "dataset_loading_assistant.yaml"
    )
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert spec["name"] == "dataset_loading_assistant"
    assert "tools" in spec
    from aqp.agents.tools import TOOL_REGISTRY

    for tool_name in spec["tools"]:
        assert tool_name in TOOL_REGISTRY, f"missing tool registration: {tool_name}"
