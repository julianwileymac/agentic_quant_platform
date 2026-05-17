"""Catalog browsing tools.

Read-only access to :class:`DatasetCatalog`, :class:`DatasetVersion`,
:class:`DatasetProfile`, and :class:`DataLineageEvent`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog, DatasetVersion
from aqp.persistence.models_lineage import DataLineageEvent
from aqp.persistence.models_pipelines import DatasetProfile


class BrowseCatalogInput(BaseModel):
    layer: str | None = Field(
        default=None,
        description="Filter by medallion layer (bronze/silver/gold). Optional.",
    )
    provider: str | None = Field(default=None, description="Filter by provider name.")
    domain: str | None = Field(default=None, description="Filter by domain.")
    search: str | None = Field(
        default=None,
        description="Free-text substring matched against name, description, semantic_definition.",
    )
    limit: int = Field(default=25, ge=1, le=200)


@register_data_mcp_tool
class BrowseCatalogTool(DataMCPTool):
    name = "data.catalog.browse"
    description = (
        "Browse the AQP DatasetCatalog. Returns a list of datasets "
        "with their medallion layer, provider, domain, business_metadata, "
        "and Iceberg identifier. Use this before calling tools that "
        "read raw bytes."
    )
    args_schema = BrowseCatalogInput
    category = "catalog"
    tags = ("catalog", "browse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        layer: str | None = None,
        provider: str | None = None,
        domain: str | None = None,
        search: str | None = None,
        limit: int = 25,
    ) -> MCPToolResult:
        with get_session() as session:
            query = select(DatasetCatalog)
            # Tenancy filter — limit results to the active workspace
            # (and rows that belong to nobody, e.g. legacy / shared
            # reference data with NULL workspace_id). When the call
            # arrives without a workspace context the query falls back
            # to NULL-only rows, preventing accidental cross-tenant
            # exposure.
            if ctx.workspace_id:
                query = query.where(
                    or_(
                        DatasetCatalog.workspace_id == ctx.workspace_id,
                        DatasetCatalog.workspace_id.is_(None),
                    )
                )
            else:
                query = query.where(DatasetCatalog.workspace_id.is_(None))
            if layer:
                query = query.where(DatasetCatalog.medallion_layer == layer)
            if provider:
                query = query.where(DatasetCatalog.provider == provider)
            if domain:
                query = query.where(DatasetCatalog.domain == domain)
            if search:
                pattern = f"%{search}%"
                query = query.where(
                    or_(
                        DatasetCatalog.name.ilike(pattern),
                        DatasetCatalog.description.ilike(pattern),
                    )
                )
            rows = (
                session.execute(query.order_by(DatasetCatalog.name).limit(limit))
                .scalars()
                .all()
            )
            data = [_row_to_dict(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"browsed {len(data)} datasets",
        )


class DescribeDatasetInput(BaseModel):
    iceberg_identifier: str = Field(
        ..., description="Full Iceberg identifier eg. aqp_silver_alpha_vantage.daily_bars"
    )


@register_data_mcp_tool
class DescribeDatasetTool(DataMCPTool):
    name = "data.catalog.describe_dataset"
    description = (
        "Return full DatasetCatalog metadata + latest DatasetVersion + "
        "DatasetProfile for one Iceberg identifier."
    )
    args_schema = DescribeDatasetInput
    category = "catalog"
    tags = ("catalog", "describe")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        iceberg_identifier: str,
    ) -> MCPToolResult:
        with get_session() as session:
            row = (
                session.execute(
                    select(DatasetCatalog).where(
                        DatasetCatalog.iceberg_identifier == iceberg_identifier
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return MCPToolResult(
                    ok=False, error=f"no catalog row for {iceberg_identifier!r}"
                )
            # Tenancy guard: when the row carries a workspace_id, refuse
            # to leak it outside that workspace. NULL workspace_id
            # rows (legacy / shared reference data) remain readable by
            # everyone with the data:read scope.
            if (
                row.workspace_id is not None
                and ctx.workspace_id is not None
                and row.workspace_id != ctx.workspace_id
            ):
                return MCPToolResult(
                    ok=False,
                    error=(
                        f"dataset {iceberg_identifier!r} belongs to a different workspace"
                    ),
                )
            latest_version = (
                session.execute(
                    select(DatasetVersion)
                    .where(DatasetVersion.catalog_id == row.id)
                    .order_by(desc(DatasetVersion.version))
                    .limit(1)
                )
                .scalars()
                .first()
            )
            ns, _, name = iceberg_identifier.rpartition(".")
            latest_profile = (
                session.execute(
                    select(DatasetProfile)
                    .where(DatasetProfile.namespace == ns)
                    .where(DatasetProfile.name == name)
                    .order_by(desc(DatasetProfile.computed_at))
                    .limit(1)
                )
                .scalars()
                .first()
            )
            payload = {
                "catalog": _row_to_dict(row),
                "latest_version": _version_to_dict(latest_version),
                "profile": _profile_to_dict(latest_profile),
            }
        return MCPToolResult(ok=True, data=payload, summary=f"described {iceberg_identifier}")


class ProfileDatasetInput(BaseModel):
    iceberg_identifier: str = Field(...)
    limit_columns: int = Field(default=20, ge=1, le=200)


@register_data_mcp_tool
class ProfileDatasetTool(DataMCPTool):
    name = "data.catalog.profile_dataset"
    description = (
        "Return the cached column statistics for an Iceberg table. "
        "Read-only; computation is deferred to the profiling pipeline."
    )
    args_schema = ProfileDatasetInput
    category = "catalog"
    tags = ("catalog", "profile")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        iceberg_identifier: str,
        limit_columns: int = 20,
    ) -> MCPToolResult:
        ns, _, name = iceberg_identifier.rpartition(".")
        with get_session() as session:
            row = (
                session.execute(
                    select(DatasetProfile)
                    .where(DatasetProfile.namespace == ns)
                    .where(DatasetProfile.name == name)
                    .order_by(desc(DatasetProfile.computed_at))
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if row is None:
                return MCPToolResult(
                    ok=False,
                    error=f"no cached profile for {iceberg_identifier!r}",
                )
            data = _profile_to_dict(row)
            if data and "columns" in data:
                data["columns"] = data["columns"][:limit_columns]
        return MCPToolResult(ok=True, data=data, summary=f"profile for {iceberg_identifier}")


class LineageOfDatasetInput(BaseModel):
    iceberg_identifier: str = Field(...)
    direction: str = Field(
        default="both",
        description="One of 'upstream', 'downstream', 'both'.",
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class LineageOfDatasetTool(DataMCPTool):
    name = "data.catalog.lineage"
    description = (
        "Return upstream / downstream lineage events for one Iceberg "
        "table. Walks the data_lineage_events graph."
    )
    args_schema = LineageOfDatasetInput
    category = "catalog"
    tags = ("catalog", "lineage")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        iceberg_identifier: str,
        direction: str = "both",
        limit: int = 50,
    ) -> MCPToolResult:
        with get_session() as session:
            query = select(DataLineageEvent)
            if direction == "upstream":
                query = query.where(DataLineageEvent.target_table_id == iceberg_identifier)
            elif direction == "downstream":
                query = query.where(DataLineageEvent.source_table_id == iceberg_identifier)
            else:
                query = query.where(
                    or_(
                        DataLineageEvent.source_table_id == iceberg_identifier,
                        DataLineageEvent.target_table_id == iceberg_identifier,
                    )
                )
            # Tenancy filter — mirror the catalog.browse policy: events
            # stamped with a workspace_id are visible only to that
            # workspace; NULL-workspace events (legacy / shared reference)
            # remain visible to everyone with the data:read scope.
            if ctx.workspace_id:
                query = query.where(
                    or_(
                        DataLineageEvent.workspace_id == ctx.workspace_id,
                        DataLineageEvent.workspace_id.is_(None),
                    )
                )
            else:
                query = query.where(DataLineageEvent.workspace_id.is_(None))
            rows = (
                session.execute(
                    query.order_by(desc(DataLineageEvent.created_at)).limit(limit)
                )
                .scalars()
                .all()
            )
            data = [_lineage_to_dict(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"{direction} lineage for {iceberg_identifier} ({len(data)} events)",
        )


def _row_to_dict(row: DatasetCatalog) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "domain": row.domain,
        "frequency": row.frequency,
        "iceberg_identifier": row.iceberg_identifier,
        "medallion_layer": row.medallion_layer,
        "business_metadata": dict(row.business_metadata or {}),
        "data_contract_json": dict(row.data_contract_json or {}),
        "tags": list(row.tags or []),
        "datahub_urn": row.datahub_urn,
        "description": row.description,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _version_to_dict(row: DatasetVersion | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "row_count": row.row_count,
        "symbol_count": row.symbol_count,
        "file_count": row.file_count,
        "dataset_hash": row.dataset_hash,
        "materialization_uri": row.materialization_uri,
        "quality_score": row.quality_score,
        "quality_breakdown": dict(row.quality_breakdown or {}),
        "as_of": row.as_of.isoformat() if row.as_of else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _profile_to_dict(row: DatasetProfile | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "namespace": row.namespace,
        "name": row.name,
        "version": row.version,
        "rows": row.rows,
        "bytes": row.bytes,
        "columns": list(row.columns or []),
        "summary": dict(row.summary or {}),
        "engine": row.engine,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


def _lineage_to_dict(row: DataLineageEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "source_table_id": row.source_table_id,
        "target_table_id": row.target_table_id,
        "transform_kind": row.transform_kind,
        "actor": row.actor,
        "actor_kind": row.actor_kind,
        "service_name": row.service_name,
        "rows_written": row.rows_written,
        "medallion_layer": row.medallion_layer,
        "summary": row.summary,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


__all__ = [
    "BrowseCatalogTool",
    "DescribeDatasetTool",
    "LineageOfDatasetTool",
    "ProfileDatasetTool",
]
