"""Data-loading tools for the dataset-loading agent.

Each tool answers a focused question the agent needs in order to
propose a pipeline manifest, source library entry, or setup wizard
step. The tools deliberately stay read-only — they probe URLs, look
up presets, and propose JSON manifests, but they never write to
Iceberg / Postgres / Kafka. The agent (or the user) is responsible
for accepting a proposal and routing it through the appropriate
``/sources``, ``/sinks``, ``/dataset-presets``, or ``/engine`` route.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# inspect_path
# ---------------------------------------------------------------------------
class InspectPathInput(BaseModel):
    path: str = Field(..., description="Local filesystem path or directory to inspect.")
    max_entries: int = Field(default=20, ge=1, le=200)


class InspectPathTool(BaseTool):
    name: str = "inspect_path"
    description: str = (
        "Walk a local filesystem path (file or directory) and return file "
        "metadata. Use this before proposing a manifest so the agent can "
        "reason about file format, size, and grouping."
    )
    args_schema: type[BaseModel] = InspectPathInput

    def _run(self, path: str, max_entries: int = 20) -> str:  # type: ignore[override]
        target = Path(path).expanduser()
        if not target.exists():
            return json.dumps({"error": f"path not found: {target}"})
        if target.is_file():
            stat = target.stat()
            return json.dumps(
                {
                    "kind": "file",
                    "path": str(target),
                    "suffix": target.suffix.lower(),
                    "size_bytes": int(stat.st_size),
                }
            )
        entries: list[dict[str, Any]] = []
        suffixes: dict[str, int] = {}
        total = 0
        for child in sorted(target.iterdir()):
            total += 1
            if child.is_file():
                suffix = child.suffix.lower()
                suffixes[suffix] = suffixes.get(suffix, 0) + 1
                if len(entries) < max_entries:
                    entries.append(
                        {
                            "kind": "file",
                            "name": child.name,
                            "suffix": suffix,
                            "size_bytes": int(child.stat().st_size),
                        }
                    )
            elif child.is_dir():
                if len(entries) < max_entries:
                    entries.append({"kind": "directory", "name": child.name})
        return json.dumps(
            {
                "kind": "directory",
                "path": str(target),
                "total_entries": total,
                "suffixes": suffixes,
                "preview": entries,
            }
        )


# ---------------------------------------------------------------------------
# peek_url
# ---------------------------------------------------------------------------
class PeekUrlInput(BaseModel):
    url: str = Field(..., description="HTTP(S) URL to probe.")
    timeout_s: float = Field(default=5.0, ge=0.5, le=30.0)
    max_bytes: int = Field(default=2048, ge=64, le=65536)


class PeekUrlTool(BaseTool):
    name: str = "peek_url"
    description: str = (
        "HEAD + truncated GET against a URL to discover content type, "
        "size, and a small payload preview. Read-only: no side effects."
    )
    args_schema: type[BaseModel] = PeekUrlInput

    def _run(self, url: str, timeout_s: float = 5.0, max_bytes: int = 2048) -> str:  # type: ignore[override]
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            return json.dumps({"error": f"httpx unavailable: {exc}"})
        try:
            with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
                head = client.head(url)
                preview = ""
                if head.status_code < 400:
                    body = client.get(url, headers={"Range": f"bytes=0-{max_bytes - 1}"})
                    preview = body.text[:max_bytes]
                return json.dumps(
                    {
                        "url": url,
                        "status_code": head.status_code,
                        "content_type": head.headers.get("content-type"),
                        "content_length": head.headers.get("content-length"),
                        "preview": preview,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"url": url, "error": str(exc)})


# ---------------------------------------------------------------------------
# lookup_dataset_preset
# ---------------------------------------------------------------------------
class LookupPresetInput(BaseModel):
    query: str = Field(..., description="Free-text or tag query.")


class LookupDatasetPresetTool(BaseTool):
    name: str = "lookup_dataset_preset"
    description: str = (
        "Search the curated dataset preset library by name, tag, or "
        "description substring. Returns a JSON list of matching presets."
    )
    args_schema: type[BaseModel] = LookupPresetInput

    def _run(self, query: str) -> str:  # type: ignore[override]
        try:
            from aqp.data.dataset_presets import list_presets
        except Exception as exc:  # pragma: no cover
            return json.dumps({"error": f"dataset_presets unavailable: {exc}"})
        q = (query or "").strip().lower()
        rows: list[dict[str, Any]] = []
        for p in list_presets():
            if q and not (
                q in p.name.lower()
                or q in p.description.lower()
                or any(q == t.lower() for t in p.tags)
            ):
                continue
            rows.append(
                {
                    "name": p.name,
                    "description": p.description,
                    "namespace": p.namespace,
                    "table": p.table,
                    "source_kind": p.source_kind,
                    "tags": list(p.tags),
                    "interval": p.interval,
                }
            )
        return json.dumps({"query": q, "results": rows})


# ---------------------------------------------------------------------------
# propose_pipeline_manifest
# ---------------------------------------------------------------------------
class ProposePipelineManifestInput(BaseModel):
    name: str
    namespace: str = "aqp"
    source_kind: str
    target_table: str
    source_kwargs: dict[str, Any] = Field(default_factory=dict)
    sink_kind: str = "iceberg"
    sink_kwargs: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ProposePipelineManifestTool(BaseTool):
    name: str = "propose_pipeline_manifest"
    description: str = (
        "Render a draft pipeline manifest dict from a natural-language "
        "description. The manifest follows the engine's NodeSpec shape; "
        "the agent presents it back for the user to accept and POST to "
        "/engine/manifests."
    )
    args_schema: type[BaseModel] = ProposePipelineManifestInput

    def _run(  # type: ignore[override]
        self,
        name: str,
        namespace: str,
        source_kind: str,
        target_table: str,
        source_kwargs: dict[str, Any] | None = None,
        sink_kind: str = "iceberg",
        sink_kwargs: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        manifest = {
            "name": name,
            "namespace": namespace,
            "tags": list(tags or []),
            "source": {
                "name": f"source.{source_kind}",
                "kwargs": dict(source_kwargs or {}),
            },
            "transforms": [],
            "sink": {
                "name": f"sink.{sink_kind}",
                "kwargs": {
                    "namespace": namespace,
                    "table": target_table,
                    **dict(sink_kwargs or {}),
                },
            },
        }
        return json.dumps(manifest, indent=2)


# ---------------------------------------------------------------------------
# propose_setup_wizard
# ---------------------------------------------------------------------------
class ProposeSetupWizardInput(BaseModel):
    source_key: str = Field(..., description="Source kind (e.g. alpha_vantage).")


class ProposeSetupWizardTool(BaseTool):
    name: str = "propose_setup_wizard"
    description: str = (
        "Look up the curated setup wizard for a source kind and return its "
        "step list as JSON for the agent (or UI) to walk through."
    )
    args_schema: type[BaseModel] = ProposeSetupWizardInput

    def _run(self, source_key: str) -> str:  # type: ignore[override]
        try:
            from aqp.data.sources.setup_wizards import get_wizard
        except Exception as exc:  # pragma: no cover
            return json.dumps({"error": f"setup_wizards unavailable: {exc}"})
        wizard = get_wizard(source_key)
        if wizard is None:
            return json.dumps({"error": f"no wizard for {source_key}"})
        return json.dumps(wizard.to_dict())


# ---------------------------------------------------------------------------
# enrich_metadata_with_dbt_artifacts
# ---------------------------------------------------------------------------
class EnrichDbtInput(BaseModel):
    project_dir: str | None = Field(default=None, description="dbt project directory.")
    target_table: str | None = Field(default=None, description="Optional table filter.")


class EnrichMetadataWithDbtTool(BaseTool):
    name: str = "enrich_metadata_with_dbt_artifacts"
    description: str = (
        "Read dbt's manifest.json + run_results.json and surface the model "
        "metadata that matches a target_table. Useful for the agent to "
        "borrow column docs from upstream dbt definitions."
    )
    args_schema: type[BaseModel] = EnrichDbtInput

    def _run(  # type: ignore[override]
        self,
        project_dir: str | None = None,
        target_table: str | None = None,
    ) -> str:
        try:
            from aqp.data.dbt.artifacts import load_manifest_models
        except Exception as exc:  # pragma: no cover
            return json.dumps({"error": f"dbt artifacts unavailable: {exc}"})
        try:
            models = load_manifest_models(project_dir=project_dir)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"manifest read failed: {exc}"})
        if target_table:
            target = str(target_table).lower()
            models = [m for m in models if target in str(m.get("name") or "").lower()]
        return json.dumps({"models": models[:50]})


# ---------------------------------------------------------------------------
# summarise_airbyte_catalog
# ---------------------------------------------------------------------------
class SummariseAirbyteInput(BaseModel):
    connector_id: str | None = Field(default=None)


class SummariseAirbyteCatalogTool(BaseTool):
    name: str = "summarise_airbyte_catalog"
    description: str = (
        "List Airbyte connectors (curated registry) and the streams each "
        "exposes. The agent uses this when proposing an Airbyte-backed "
        "pipeline as an alternative to a custom fetcher."
    )
    args_schema: type[BaseModel] = SummariseAirbyteInput

    def _run(self, connector_id: str | None = None) -> str:  # type: ignore[override]
        try:
            from aqp.data.airbyte.registry import list_connectors
        except Exception as exc:  # pragma: no cover
            return json.dumps({"error": f"airbyte registry unavailable: {exc}"})
        try:
            connectors = list_connectors()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"list_connectors failed: {exc}"})
        rows: list[dict[str, Any]] = []
        for c in connectors:
            if connector_id and getattr(c, "id", "") != connector_id:
                continue
            try:
                rows.append(
                    {
                        "id": getattr(c, "id", ""),
                        "name": getattr(c, "name", ""),
                        "kind": str(getattr(c, "kind", "")),
                        "runtime": str(getattr(c, "runtime", "")),
                        "tags": list(getattr(c, "tags", []) or []),
                        "streams": [
                            getattr(s, "name", "") for s in (getattr(c, "streams", []) or [])
                        ],
                    }
                )
            except Exception:  # noqa: BLE001
                rows.append({"id": getattr(c, "id", str(c))})
        return json.dumps({"connectors": rows[:100]})


__all__ = [
    "EnrichMetadataWithDbtTool",
    "InspectPathTool",
    "LookupDatasetPresetTool",
    "PeekUrlTool",
    "ProposePipelineManifestTool",
    "ProposeSetupWizardTool",
    "SummariseAirbyteCatalogTool",
]
