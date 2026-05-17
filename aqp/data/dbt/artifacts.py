"""Helpers for reading dbt artifacts into AQP-friendly shapes."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


def artifact_paths(project_dir: Path | str | None = None) -> dict[str, str | None]:
    """Return known dbt artifact paths, with missing artifacts as ``None``."""
    target = Path(project_dir or settings.dbt_project_dir).expanduser().resolve() / "target"
    paths = {
        "manifest": target / "manifest.json",
        "catalog": target / "catalog.json",
        "run_results": target / "run_results.json",
    }
    return {name: str(path) if path.exists() else None for name, path in paths.items()}


def load_manifest_models(project_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Load models, seeds, and sources from ``target/manifest.json``."""
    manifest = _load_artifact(project_dir, "manifest.json")
    if not manifest:
        return []

    rows: list[dict[str, Any]] = []
    for unique_id, node in sorted((manifest.get("nodes") or {}).items()):
        resource_type = node.get("resource_type")
        if resource_type not in {"model", "seed", "snapshot", "test"}:
            continue
        rows.append(_node_summary(unique_id, node))

    for unique_id, source in sorted((manifest.get("sources") or {}).items()):
        rows.append(_node_summary(unique_id, source, resource_type="source"))
    return rows


def load_model_detail(unique_id: str, project_dir: Path | str | None = None) -> dict[str, Any] | None:
    """Return one manifest node/source by unique id."""
    manifest = _load_artifact(project_dir, "manifest.json")
    if not manifest:
        return None
    raw = (manifest.get("nodes") or {}).get(unique_id) or (manifest.get("sources") or {}).get(unique_id)
    if not raw:
        return None
    return {
        **_node_summary(unique_id, raw, resource_type=raw.get("resource_type")),
        "raw": raw,
    }


def load_run_results(project_dir: Path | str | None = None) -> dict[str, Any]:
    """Load ``run_results.json`` with a compact derived summary."""
    payload = _load_artifact(project_dir, "run_results.json")
    if not payload:
        return {"results": [], "elapsed_time": None, "generated_at": None}
    results = []
    for result in payload.get("results") or []:
        results.append(
            {
                "unique_id": result.get("unique_id"),
                "status": result.get("status"),
                "execution_time": result.get("execution_time"),
                "message": result.get("message"),
                "adapter_response": result.get("adapter_response") or {},
                "failures": result.get("failures"),
            }
        )
    return {
        "results": results,
        "elapsed_time": payload.get("elapsed_time"),
        "generated_at": (payload.get("metadata") or {}).get("generated_at"),
        "args": payload.get("args") or {},
    }


def _load_artifact(project_dir: Path | str | None, name: str) -> dict[str, Any]:
    path = Path(project_dir or settings.dbt_project_dir).expanduser().resolve() / "target" / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("failed to read dbt artifact %s", path, exc_info=True)
        return {}


def _node_summary(
    unique_id: str,
    node: dict[str, Any],
    *,
    resource_type: str | None = None,
) -> dict[str, Any]:
    config = node.get("config") or {}
    return {
        "unique_id": unique_id,
        "name": node.get("name"),
        "alias": node.get("alias"),
        "database": node.get("database"),
        "schema": node.get("schema"),
        "resource_type": resource_type or node.get("resource_type"),
        "package_name": node.get("package_name"),
        "path": node.get("path"),
        "original_file_path": node.get("original_file_path"),
        "description": node.get("description"),
        "tags": list(node.get("tags") or []),
        "materialized": config.get("materialized"),
        "depends_on": (node.get("depends_on") or {}).get("nodes") or [],
        "columns": list((node.get("columns") or {}).keys()),
        "meta": node.get("meta") or {},
    }
