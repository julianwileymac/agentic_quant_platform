"""``data.dbt.*`` DataMCP tools (Phase 2 — dbt plane, plan section 6).

Three read-only tools surfacing the dbt mesh:

- ``data.dbt.list_models`` — enumerate models from the active
  manifest (filtered by project / access modifier / tag).
- ``data.dbt.describe_model`` — full metadata: columns,
  description, contracts, tests, depends_on, lineage.
- ``data.dbt.lineage_for_model`` — upstream + downstream walk
  via the manifest's ``parent_map`` / ``child_map``.

The tools read manifests from the dbt-loom S3 registry (Phase 2
:mod:`aqp.data.dbt.loom_registry`) so they work across the entire
mesh, not just the locally-compiled project.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


def _load_manifest(project_slug: str) -> dict[str, Any] | None:
    """Resolve the manifest.json for a project.

    Order: (1) local target path; (2) dbt-loom S3 registry.
    Returns ``None`` on miss; the tools surface a clear error in
    that case rather than crash.
    """
    candidates: list[Path] = [
        Path(f"aqp/data/dbt/projects/{project_slug}/target/manifest.json"),
        Path(f"target/manifest.json"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not parse %s: %s", path, exc)
    # S3 fallback — only attempts when boto3 is available.
    try:
        from aqp.config import settings

        bucket = getattr(settings, "dbt_loom_bucket", None)
        if not bucket:
            return None
        import boto3  # type: ignore[import-not-found]

        s3 = boto3.client("s3")
        env = str(getattr(settings, "deployment_env", "prod"))
        key = f"{env}/aqp_dbt_{project_slug}/manifest.json"
        obj = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("manifest s3 fallback failed for %s: %s", project_slug, exc)
        return None


# ---------------------------------------------------------------------------
# Tool 1: list_models
# ---------------------------------------------------------------------------


class ListModelsInput(BaseModel):
    project_slug: str = Field(default="core")
    access: str | None = Field(
        default=None,
        description="Filter to one access modifier (public|protected|private).",
    )
    tag: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)


@register_data_mcp_tool
class DbtListModelsTool(DataMCPTool):
    """Enumerate dbt models from the loom-published manifest."""

    name = "data.dbt.list_models"
    description = (
        "List dbt models from the active manifest. Filters: project_slug "
        "(core / equities / derivatives / macro), access (public / "
        "protected / private), tag. Read-only."
    )
    args_schema = ListModelsInput
    category = "dbt"
    tags = ("dbt", "models", "catalog")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        project_slug: str = "core",
        access: str | None = None,
        tag: str | None = None,
        limit: int = 200,
    ) -> MCPToolResult:
        manifest = _load_manifest(project_slug)
        if manifest is None:
            return MCPToolResult(
                ok=False,
                error=f"no manifest available for project {project_slug!r}",
            )
        nodes: dict[str, Any] = manifest.get("nodes", {}) or {}
        out: list[dict[str, Any]] = []
        for unique_id, node in nodes.items():
            if not unique_id.startswith("model."):
                continue
            cfg = node.get("config", {}) or {}
            if access and str(cfg.get("access", "protected")) != access:
                continue
            if tag and tag not in (cfg.get("tags") or []):
                continue
            out.append(
                {
                    "unique_id": unique_id,
                    "name": node.get("name"),
                    "schema": node.get("schema"),
                    "materialized": cfg.get("materialized"),
                    "access": cfg.get("access", "protected"),
                    "tags": list(cfg.get("tags") or []),
                    "description": node.get("description", ""),
                }
            )
            if len(out) >= limit:
                break
        return MCPToolResult(
            ok=True,
            data={"models": out},
            summary=f"{len(out)} model(s) in {project_slug}",
            rows_returned=len(out),
        )


# ---------------------------------------------------------------------------
# Tool 2: describe_model
# ---------------------------------------------------------------------------


class DescribeModelInput(BaseModel):
    project_slug: str = Field(default="core")
    unique_id: str = Field(
        description="Full dbt unique_id (e.g. model.aqp_dbt_core.fct_equity_minute_bars)."
    )


@register_data_mcp_tool
class DbtDescribeModelTool(DataMCPTool):
    """Return full metadata for one dbt model."""

    name = "data.dbt.describe_model"
    description = (
        "Return columns, description, contract, tests, and depends_on for one "
        "dbt model from the loom manifest."
    )
    args_schema = DescribeModelInput
    category = "dbt"
    tags = ("dbt", "models")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        project_slug: str = "core",
        unique_id: str,
    ) -> MCPToolResult:
        manifest = _load_manifest(project_slug)
        if manifest is None:
            return MCPToolResult(
                ok=False,
                error=f"no manifest available for project {project_slug!r}",
            )
        node = (manifest.get("nodes") or {}).get(unique_id)
        if node is None:
            return MCPToolResult(
                ok=False, error=f"unknown model {unique_id!r}"
            )
        return MCPToolResult(
            ok=True,
            data={
                "unique_id": unique_id,
                "name": node.get("name"),
                "schema": node.get("schema"),
                "config": node.get("config", {}),
                "columns": node.get("columns", {}),
                "description": node.get("description", ""),
                "depends_on": node.get("depends_on", {}),
                "refs": node.get("refs", []),
                "sources": node.get("sources", []),
                "contract": (node.get("contract") or {}),
            },
            summary=f"described {unique_id}",
        )


# ---------------------------------------------------------------------------
# Tool 3: lineage_for_model
# ---------------------------------------------------------------------------


class LineageForModelInput(BaseModel):
    project_slug: str = Field(default="core")
    unique_id: str
    depth: int = Field(default=2, ge=1, le=10)
    direction: str = Field(
        default="both",
        description="upstream | downstream | both",
    )


@register_data_mcp_tool
class DbtLineageForModelTool(DataMCPTool):
    """Walk the parent / child map for one model up to ``depth`` hops."""

    name = "data.dbt.lineage_for_model"
    description = (
        "Walk the dbt parent_map / child_map for one model. depth=2 by "
        "default; direction is upstream / downstream / both."
    )
    args_schema = LineageForModelInput
    category = "dbt"
    tags = ("dbt", "lineage")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        project_slug: str = "core",
        unique_id: str,
        depth: int = 2,
        direction: str = "both",
    ) -> MCPToolResult:
        manifest = _load_manifest(project_slug)
        if manifest is None:
            return MCPToolResult(
                ok=False,
                error=f"no manifest available for project {project_slug!r}",
            )
        parent_map: dict[str, list[str]] = manifest.get("parent_map") or {}
        child_map: dict[str, list[str]] = manifest.get("child_map") or {}

        def _walk(
            start: str, edges: dict[str, list[str]], depth: int
        ) -> list[str]:
            seen = {start}
            frontier = [start]
            for _ in range(depth):
                next_frontier: list[str] = []
                for node in frontier:
                    for neighbour in edges.get(node, []) or []:
                        if neighbour in seen:
                            continue
                        seen.add(neighbour)
                        next_frontier.append(neighbour)
                frontier = next_frontier
            seen.discard(start)
            return sorted(seen)

        out: dict[str, list[str]] = {}
        if direction in ("upstream", "both"):
            out["upstream"] = _walk(unique_id, parent_map, depth)
        if direction in ("downstream", "both"):
            out["downstream"] = _walk(unique_id, child_map, depth)
        return MCPToolResult(
            ok=True,
            data={"unique_id": unique_id, "depth": depth, **out},
            summary=(
                f"{len(out.get('upstream', []))} upstream + "
                f"{len(out.get('downstream', []))} downstream"
            ),
        )


__all__ = [
    "DbtDescribeModelTool",
    "DbtLineageForModelTool",
    "DbtListModelsTool",
]
