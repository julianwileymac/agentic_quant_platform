"""DataHub DataMCP tools."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog
from aqp.persistence.models_pipelines import DatahubSyncLog


class LookupDatahubUrnInput(BaseModel):
    urn: str | None = None
    iceberg_identifier: str | None = None


@register_data_mcp_tool
class LookupDatahubUrnTool(DataMCPTool):
    name = "data.datahub.lookup"
    description = (
        "Look up a DataHub URN attached to an AQP DatasetCatalog row, or "
        "the inverse — resolve an iceberg_identifier to its URN."
    )
    args_schema = LookupDatahubUrnInput
    category = "datahub"
    tags = ("datahub",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        urn: str | None = None,
        iceberg_identifier: str | None = None,
    ) -> MCPToolResult:
        if not urn and not iceberg_identifier:
            return MCPToolResult(
                ok=False, error="must provide either 'urn' or 'iceberg_identifier'"
            )
        with get_session() as session:
            query = select(DatasetCatalog)
            if urn:
                query = query.where(DatasetCatalog.datahub_urn == urn)
            elif iceberg_identifier:
                query = query.where(
                    DatasetCatalog.iceberg_identifier == iceberg_identifier
                )
            row = session.execute(query.limit(1)).scalars().first()
            if row is None:
                return MCPToolResult(ok=False, error="no matching catalog row")
            data = {
                "id": row.id,
                "name": row.name,
                "iceberg_identifier": row.iceberg_identifier,
                "datahub_urn": row.datahub_urn,
                "provider": row.provider,
                "domain": row.domain,
                "medallion_layer": row.medallion_layer,
            }
        return MCPToolResult(ok=True, data=data, summary="datahub urn resolved")


class SyncDatahubInput(BaseModel):
    direction: str = Field(default="push", description="push or pull")
    iceberg_identifier: str | None = None


@register_data_mcp_tool
class SyncDatahubTool(DataMCPTool):
    name = "data.datahub.sync"
    description = (
        "Trigger a DataHub sync (push AQP catalog out, or pull DataHub "
        "metadata in). Requires data:write scope."
    )
    args_schema = SyncDatahubInput
    category = "datahub"
    tags = ("datahub", "mutating")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        direction: str = "push",
        iceberg_identifier: str | None = None,
    ) -> MCPToolResult:
        if direction not in {"push", "pull"}:
            return MCPToolResult(
                ok=False, error=f"direction must be 'push' or 'pull', got {direction!r}"
            )
        try:
            from aqp.tasks.datahub_tasks import sync_datahub_async  # type: ignore[import-not-found]
        except ImportError:
            return MCPToolResult(
                ok=False, error="datahub task module unavailable in this build"
            )
        try:
            celery_result = sync_datahub_async.delay(
                direction=direction,
                iceberg_identifier=iceberg_identifier,
            )
            return MCPToolResult(
                ok=True,
                data={
                    "task_id": str(celery_result.id),
                    "direction": direction,
                    "iceberg_identifier": iceberg_identifier,
                },
                summary=f"queued datahub {direction}",
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"queue failed: {exc}")


class DatahubSyncLogInput(BaseModel):
    direction: str | None = None
    limit: int = Field(default=20, ge=1, le=200)


@register_data_mcp_tool
class DatahubSyncLogTool(DataMCPTool):
    name = "data.datahub.sync_log"
    description = "Return recent DataHub sync log entries (push / pull cycles)."
    args_schema = DatahubSyncLogInput
    category = "datahub"
    tags = ("datahub", "audit")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        direction: str | None = None,
        limit: int = 20,
    ) -> MCPToolResult:
        with get_session() as session:
            query = select(DatahubSyncLog)
            if direction:
                query = query.where(DatahubSyncLog.direction == direction)
            rows = (
                session.execute(query.order_by(desc(DatahubSyncLog.started_at)).limit(limit))
                .scalars()
                .all()
            )
            data = [
                {
                    "id": row.id,
                    "direction": row.direction,
                    "target": row.target,
                    "urn": row.urn,
                    "platform": row.platform,
                    "status": row.status,
                    "error": row.error,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in rows
            ]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"datahub sync log ({len(data)} rows)",
        )


__all__ = [
    "DatahubSyncLogTool",
    "LookupDatahubUrnTool",
    "SyncDatahubTool",
]
