"""DataHub DataMCP tools."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select

from aqp.config import settings
from aqp.data.datahub.aspect_emitter import push_all_aspects, push_aspect
from aqp.data.datahub.aspect_mapping import (
    ASPECT_TO_DATAHUB_CLASS,
    aqp_urn_to_datahub_entity_urn,
)
from aqp.data.datahub.aspect_puller import pull_all_aspects, pull_aspect
from aqp.data.datahub.sync import sync_aspects
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity
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
    include_aspects: bool = Field(
        default=False,
        description=(
            "When true, also sync aspect-store metadata through datahub.sync_aspects."
        ),
    )


class EmitAspectToDatahubInput(BaseModel):
    urn: str
    aspect_name: str
    version: int | None = None


@register_data_mcp_tool
class EmitAspectToDatahubTool(DataMCPTool):
    name = "data.datahub.emit_aspect"
    description = (
        "Push a single EntityAspect row to DataHub via "
        "MetadataChangeProposalWrapper. Routes through to_datahub_urn() "
        "for URN translation. Requires "
        "AQP_DATAHUB_ASPECT_PUSH_ENABLED=true."
    )
    args_schema = EmitAspectToDatahubInput
    category = "datahub"
    tags = ("datahub", "mutating", "aspects")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        urn: str,
        aspect_name: str,
        version: int | None = None,
    ) -> MCPToolResult:
        if not getattr(settings, "datahub_aspect_push_enabled", True):
            return MCPToolResult(
                ok=False,
                error=(
                    "AQP_DATAHUB_ASPECT_PUSH_ENABLED=false; enable aspect push "
                    "to use data.datahub.emit_aspect"
                ),
            )
        # Tenancy check (rule 33): confirm the row is visible to the caller
        # before delegating to push_aspect, which itself re-filters via
        # _apply_tenancy_filters from the active context.
        with get_session() as session:
            stmt = select(EntityAspect).where(
                EntityAspect.urn == urn,
                EntityAspect.aspect_name == aspect_name,
            )
            if ctx.workspace_id:
                stmt = stmt.where(
                    or_(
                        EntityAspect.workspace_id == ctx.workspace_id,
                        EntityAspect.workspace_id.is_(None),
                    )
                )
            else:
                stmt = stmt.where(EntityAspect.workspace_id.is_(None))
            if version is None:
                stmt = stmt.order_by(desc(EntityAspect.version)).limit(1)
            else:
                stmt = stmt.where(EntityAspect.version == int(version)).limit(1)
            row = session.execute(stmt).scalars().first()
            if row is None:
                return MCPToolResult(
                    ok=False,
                    error=(
                        "EntityAspect row not found for "
                        f"urn={urn!r}, aspect_name={aspect_name!r}, version={version!r}"
                    ),
                )
        result = push_aspect(
            urn=row.urn,
            aspect_name=row.aspect_name,
            version=row.version,
        )
        ok = bool(result.get("emitted"))
        return MCPToolResult(
            ok=ok,
            data=result,
            summary="emitted DataHub aspect" if ok else "failed DataHub aspect emit",
            error=None if ok else str(result.get("error") or "emit failed"),
        )


class PullAspectsFromDatahubInput(BaseModel):
    datahub_urn: str
    aspect_names: list[str] | None = None


class AspectSyncArgs(BaseModel):
    direction: Literal["push", "pull"]
    urn: str | None = Field(
        default=None,
        description=(
            "If set, sync only this URN. Accepts either AQP URNs "
            "(urn:aqp:...) or DataHub URNs (urn:li:...)."
        ),
    )
    aspect_name: str | None = Field(
        default=None,
        description="Optional aspect name filter when syncing a single URN.",
    )
    entity_type: str | None = Field(
        default=None,
        description=(
            "Optional entity type filter for workspace-wide sync "
            "(dataset, mlmodel, pipeline, ...)."
        ),
    )


@register_data_mcp_tool
class PullAspectsFromDatahubTool(DataMCPTool):
    name = "data.datahub.pull_aspects"
    description = (
        "Pull DataHub aspects into the AQP entity_aspects store for a given "
        "DataHub URN. Requires AQP_DATAHUB_ASPECT_PULL_ENABLED=true."
    )
    args_schema = PullAspectsFromDatahubInput
    category = "datahub"
    tags = ("datahub", "mutating", "aspects")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        datahub_urn: str,
        aspect_names: list[str] | None = None,
    ) -> MCPToolResult:
        if not getattr(settings, "datahub_aspect_pull_enabled", True):
            return MCPToolResult(
                ok=False,
                error=(
                    "AQP_DATAHUB_ASPECT_PULL_ENABLED=false; enable aspect pull "
                    "to use data.datahub.pull_aspects"
                ),
            )
        if aspect_names:
            results: list[dict[str, Any]] = []
            for aspect_name in aspect_names:
                aspect_class = ASPECT_TO_DATAHUB_CLASS.get(aspect_name)
                if not aspect_class:
                    results.append(
                        {
                            "ok": False,
                            "aspect_name": aspect_name,
                            "error": (
                                f"unknown aspect_name for DataHub sync: {aspect_name!r}"
                            ),
                        }
                    )
                    continue
                result = pull_aspect(
                    datahub_urn=datahub_urn,
                    aspect_class_name=aspect_class,
                )
                results.append({**result, "ok": bool(result.get("pulled"))})
        else:
            bulk = pull_all_aspects(datahub_urn=datahub_urn)
            sub_results = bulk.get("results") or []
            results = [
                {**row, "ok": bool(row.get("pulled"))} for row in sub_results
            ]
            if bulk.get("error"):
                results.append(
                    {"ok": False, "error": str(bulk["error"]), "datahub_urn": datahub_urn}
                )
        failures = [row for row in results if not row.get("ok")]
        return MCPToolResult(
            ok=not failures,
            data=results,
            rows_returned=len(results),
            summary=f"pulled {len(results)} aspect rows from DataHub",
            error=None if not failures else f"{len(failures)} aspects failed to persist",
        )


@register_data_mcp_tool
class AspectSyncDatahubTool(DataMCPTool):
    name = "data.datahub.aspect_sync"
    description = (
        "Push AQP EntityAspect rows to DataHub (or pull DataHub aspects into AQP). "
        "Set direction='push' to emit AQP aspects as MetadataChangeProposal events; "
        "direction='pull' to import DataHub aspects into entity_aspects via write_aspect()."
    )
    args_schema = AspectSyncArgs
    category = "datahub"
    tags = ("datahub", "metadata", "mutating")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        direction: Literal["push", "pull"],
        urn: str | None = None,
        aspect_name: str | None = None,
        entity_type: str | None = None,
    ) -> MCPToolResult:
        if direction == "push":
            if urn:
                result = push_aspect(urn=urn, aspect_name=aspect_name)
                ok = bool(result.get("emitted"))
                return MCPToolResult(
                    ok=ok,
                    data=result,
                    summary="pushed aspects for one URN" if ok else "aspect push failed",
                    error=None if ok else str(result.get("error") or "aspect push failed"),
                )
            result = push_all_aspects(entity_type=entity_type)
            ok = not bool(result.get("errors"))
            return MCPToolResult(
                ok=ok,
                data=result,
                summary="pushed workspace aspects",
                error=None if ok else "; ".join(str(err) for err in (result.get("errors") or [])),
            )

        if urn:
            datahub_urn = urn if urn.startswith("urn:li:") else aqp_urn_to_datahub_entity_urn(urn)
            if aspect_name:
                aspect_class_name = ASPECT_TO_DATAHUB_CLASS.get(aspect_name)
                if not aspect_class_name:
                    return MCPToolResult(
                        ok=False,
                        error=f"unknown aspect_name for DataHub sync: {aspect_name!r}",
                    )
                result = pull_aspect(
                    datahub_urn=datahub_urn,
                    aspect_class_name=aspect_class_name,
                )
                ok = bool(result.get("pulled"))
                return MCPToolResult(
                    ok=ok,
                    data=result,
                    summary="pulled one DataHub aspect" if ok else "aspect pull failed",
                    error=None if ok else str(result.get("error") or "aspect pull failed"),
                )
            result = pull_all_aspects(datahub_urn=datahub_urn)
            ok = bool(result.get("pulled")) and not bool(result.get("errors"))
            return MCPToolResult(
                ok=ok,
                data=result,
                summary="pulled all DataHub aspects for URN",
                error=(
                    None
                    if ok
                    else str(result.get("error") or "; ".join(result.get("errors") or []))
                ),
            )

        with get_session() as session:
            stmt = select(MetadataEntity.urn).distinct()
            if entity_type:
                stmt = stmt.where(MetadataEntity.entity_type == entity_type)
            if ctx.workspace_id:
                stmt = stmt.where(
                    or_(
                        MetadataEntity.workspace_id == ctx.workspace_id,
                        MetadataEntity.workspace_id.is_(None),
                    )
                )
            else:
                stmt = stmt.where(MetadataEntity.workspace_id.is_(None))
            if ctx.project_id:
                stmt = stmt.where(
                    or_(
                        MetadataEntity.project_id == ctx.project_id,
                        MetadataEntity.project_id.is_(None),
                    )
                )
            aqp_urns = [str(value) for value in session.execute(stmt).scalars().all() if value]

        pulled_count = 0
        errors: list[str] = []
        results: list[dict[str, Any]] = []
        for aqp_urn in aqp_urns:
            result = pull_all_aspects(
                datahub_urn=aqp_urn_to_datahub_entity_urn(aqp_urn)
            )
            results.append(result)
            pulled_count += int(result.get("pulled_count") or 0)
            if result.get("error"):
                errors.append(str(result["error"]))
            errors.extend(str(err) for err in (result.get("errors") or []))

        ok = not errors
        return MCPToolResult(
            ok=ok,
            data={
                "urns_scanned": len(aqp_urns),
                "pulled_count": pulled_count,
                "errors": errors,
                "results": results,
            },
            summary="pulled DataHub aspects for workspace URNs",
            error=None if ok else "; ".join(errors[:5]),
        )


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
        include_aspects: bool = False,
    ) -> MCPToolResult:
        if direction not in {"push", "pull"}:
            return MCPToolResult(
                ok=False, error=f"direction must be 'push' or 'pull', got {direction!r}"
            )
        if include_aspects:
            from aqp.data.datahub.emitter import push_all
            from aqp.data.datahub.puller import pull_external

            try:
                # Plumb the caller's tenancy into sync_aspects so a push from
                # a workspace-scoped MCP context never emits another tenant's
                # aspects to a shared DataHub instance (rule 33).
                if direction == "push":
                    data: dict[str, Any] = {"push": push_all()}
                    aspects = sync_aspects(
                        push=True,
                        pull=False,
                        workspace_id=ctx.workspace_id,
                        project_id=ctx.project_id,
                    )
                else:
                    data = {"pull": pull_external()}
                    aspects = sync_aspects(
                        push=False,
                        pull=True,
                        workspace_id=ctx.workspace_id,
                        project_id=ctx.project_id,
                    )
                data["aspects"] = aspects
                return MCPToolResult(
                    ok=True,
                    data=data,
                    summary=f"completed datahub {direction} + aspect sync",
                )
            except Exception as exc:  # noqa: BLE001
                return MCPToolResult(ok=False, error=f"sync failed: {exc}")
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
    "AspectSyncDatahubTool",
    "DatahubSyncLogTool",
    "EmitAspectToDatahubTool",
    "LookupDatahubUrnTool",
    "PullAspectsFromDatahubTool",
    "SyncDatahubTool",
]
