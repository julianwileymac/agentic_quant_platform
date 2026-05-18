"""Read-only DataMCP tools for the Assistant Engine.

Four tools exposed through both the in-process bridge (auto-merged
into :data:`aqp.agents.tools.TOOL_REGISTRY` so spec-driven agents can
read assistant state) and the external ``aqp-data-mcp`` stdio binary:

- ``data.assistants.list`` — registered :class:`AssistantSpec` entries.
- ``data.assistants.describe`` — full spec payload for one assistant.
- ``data.assistants.get_run`` — persisted run + structured events.
- ``data.assistants.health`` — run-status counts for dashboards.

All four are mutates=False / required_scopes=("data:read",) and degrade
cleanly when the Phase 2 ``assistant_*`` tables aren't yet provisioned
so the legacy DataMCP catalog stays usable on a fresh DB.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


class _AssistantNameInput(BaseModel):
    name: str = Field(..., description="AssistantSpec name (registry slug).")


class _AssistantRunInput(BaseModel):
    run_id: str = Field(..., description="Assistant run id (UUID).")


def _filter_by_tenant(query: Any, ctx: MCPToolContext, model: Any) -> Any:
    """Tenancy filter for ``ProjectScopedMixin``-backed rows.

    When ``ctx.workspace_id`` is set we narrow to that workspace; the
    rule prevents an agent that knows a run id from another tenant
    from reading the row by guessing.
    """
    if ctx.workspace_id and hasattr(model, "workspace_id"):
        query = query.filter(model.workspace_id == ctx.workspace_id)
    return query


@register_data_mcp_tool
class ListAssistantsTool(DataMCPTool):
    name = "data.assistants.list"
    description = (
        "List registered AssistantSpec entries (name, mode, target ref, "
        "snapshot hash). Read-only catalog browser used by the Studio + "
        "agent ideation loops."
    )
    args_schema = None
    category = "assistants"
    tags = ("assistants", "read")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.assistants.registry import list_assistant_specs

        specs = [
            {
                "name": spec.name,
                "description": spec.description,
                "mode": spec.mode,
                "target_kind": spec.target_kind,
                "target_ref": spec.target_ref,
                "snapshot_hash": spec.snapshot_hash(),
                "annotations": list(spec.annotations or []),
                "template_target": getattr(spec, "template_target", "utility"),
            }
            for spec in list_assistant_specs()
        ]
        return MCPToolResult(ok=True, data=specs, rows_returned=len(specs))


@register_data_mcp_tool
class DescribeAssistantTool(DataMCPTool):
    name = "data.assistants.describe"
    description = (
        "Return the full payload + policy fields for one AssistantSpec. "
        "Equivalent to the GET /assistants/{name} HTTP route."
    )
    args_schema = _AssistantNameInput
    category = "assistants"
    tags = ("assistants", "read")

    def run(
        self, *, ctx: MCPToolContext, name: str, **arguments: Any
    ) -> MCPToolResult:
        from aqp.assistants.registry import get_assistant_spec

        try:
            spec = get_assistant_spec(name)
        except KeyError as exc:
            return MCPToolResult(ok=False, error=str(exc))
        return MCPToolResult(
            ok=True,
            data=spec.model_dump(mode="json"),
            rows_returned=1,
        )


@register_data_mcp_tool
class GetAssistantRunTool(DataMCPTool):
    name = "data.assistants.get_run"
    description = (
        "Fetch one assistant run + its structured event timeline. "
        "Tenancy is enforced when the caller carries a workspace_id."
    )
    args_schema = _AssistantRunInput
    category = "assistants"
    tags = ("assistants", "runs", "read")

    def run(
        self, *, ctx: MCPToolContext, run_id: str, **arguments: Any
    ) -> MCPToolResult:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_assistants import (
                AssistantRun,
                AssistantRunEvent,
            )
        except Exception:  # noqa: BLE001
            return MCPToolResult(
                ok=True,
                data={"table_present": False, "run": None, "events": []},
                rows_returned=0,
            )
        try:
            with get_session() as session:
                base = _filter_by_tenant(
                    session.query(AssistantRun), ctx, AssistantRun
                )
                row = base.filter(AssistantRun.id == run_id).one_or_none()
                if row is None:
                    return MCPToolResult(
                        ok=False, error=f"assistant run {run_id!r} not found"
                    )
                events = (
                    session.query(AssistantRunEvent)
                    .filter(AssistantRunEvent.run_id == run_id)
                    .order_by(AssistantRunEvent.seq)
                    .all()
                )
                return MCPToolResult(
                    ok=True,
                    data={
                        "table_present": True,
                        "run": {
                            "id": str(row.id),
                            "assistant_spec_name": row.assistant_spec_name,
                            "status": row.status,
                            "target_kind": row.target_kind,
                            "target_ref": row.target_ref,
                            "target_run_kind": row.target_run_kind,
                            "target_run_id": row.target_run_id,
                            "cost_usd": float(row.cost_usd or 0.0),
                            "n_calls": int(row.n_calls or 0),
                            "n_tool_calls": int(row.n_tool_calls or 0),
                            "n_rag_hits": int(row.n_rag_hits or 0),
                            "halted": bool(row.halted),
                            "started_at": str(row.started_at)
                            if row.started_at
                            else None,
                            "completed_at": str(row.completed_at)
                            if row.completed_at
                            else None,
                            "duration_ms": float(row.duration_ms)
                            if row.duration_ms is not None
                            else None,
                            "output": dict(row.output or {}),
                            "error": row.error,
                        },
                        "events": [
                            {
                                "seq": event.seq,
                                "kind": event.kind,
                                "name": event.name,
                                "attributes": dict(event.attributes or {}),
                                "status": event.status,
                                "cost_usd": (
                                    float(event.cost_usd)
                                    if event.cost_usd is not None
                                    else None
                                ),
                                "duration_ms": (
                                    float(event.duration_ms)
                                    if event.duration_ms is not None
                                    else None
                                ),
                                "error": event.error,
                                "created_at": (
                                    str(event.created_at)
                                    if event.created_at
                                    else None
                                ),
                            }
                            for event in events
                        ],
                    },
                    rows_returned=1,
                )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")


@register_data_mcp_tool
class AssistantHealthTool(DataMCPTool):
    name = "data.assistants.health"
    description = (
        "Summarise assistant_run status counts (running / pending / "
        "halted / error / completed) for the active workspace. Used by "
        "the assistant watchdog dashboard."
    )
    args_schema = None
    category = "assistants"
    tags = ("assistants", "health", "read")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_assistants import AssistantRun
        except Exception:  # noqa: BLE001
            return MCPToolResult(
                ok=True,
                data={
                    "table_present": False,
                    "running": 0,
                    "pending": 0,
                    "halted": 0,
                    "error": 0,
                    "completed": 0,
                },
            )
        counts: dict[str, Any] = {"table_present": True}
        try:
            with get_session() as session:
                for status in ("running", "pending", "halted", "error", "completed"):
                    q = _filter_by_tenant(
                        session.query(AssistantRun).filter(
                            AssistantRun.status == status
                        ),
                        ctx,
                        AssistantRun,
                    )
                    counts[status] = q.count()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=str(exc))
        return MCPToolResult(ok=True, data=counts)


__all__ = [
    "AssistantHealthTool",
    "DescribeAssistantTool",
    "GetAssistantRunTool",
    "ListAssistantsTool",
]
