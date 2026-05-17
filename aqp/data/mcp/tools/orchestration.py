"""``data.orchestration.*`` DataMCP tools.

Read-only surface that lets agents (and the studio UI) inspect the
orchestration control plane without bypassing AGENTS rule 22.

Tools shipped:

- ``data.orchestration.list_adapters`` — every registered
  :class:`aqp.agents.orchestration.OrchestrationAdapter`. Always
  available — backed by the in-memory registry so even cold installs
  without the Phase 5 persistence tables return a non-empty payload.
- ``data.orchestration.list_runs`` — recent ``workflow_runs`` rows.
  Falls back to an empty list when the Phase 5 table hasn't shipped.
- ``data.orchestration.get_run`` — single ``workflow_runs`` row by id.
- ``data.orchestration.list_workflows`` — registered ``WorkflowSpec``
  entries (in-memory + persisted rows when present).
- ``data.orchestration.fusion_inputs_for_run`` — Phase 4 fusion-input
  snapshot for a specific run (read-only audit hook).

Every tool is read-only and requires the default ``data:read`` scope.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# data.orchestration.list_adapters
# ----------------------------------------------------------------------------


class _NoArgs(BaseModel):
    """No arguments."""


@register_data_mcp_tool
class OrchestrationListAdaptersTool(DataMCPTool):
    name = "data.orchestration.list_adapters"
    description = (
        "Return every registered OrchestrationAdapter (alias, kind, "
        "tags, source). Backed by the in-process metaclass registry "
        "so this works in cold installs even before the Phase 5 "
        "persistence tables exist."
    )
    args_schema = _NoArgs
    category = "orchestration"
    tags = ("orchestration", "adapters", "catalog")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, **_: object) -> MCPToolResult:
        try:
            from aqp.agents.orchestration.registry import describe_adapter_catalog
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"orchestration registry unavailable: {exc}",
                summary="registry import failed",
            )
        catalog = describe_adapter_catalog()
        return MCPToolResult(
            ok=True,
            data={"adapters": catalog},
            rows_returned=len(catalog),
            summary=f"{len(catalog)} adapter(s) registered",
        )


# ----------------------------------------------------------------------------
# data.orchestration.list_runs
# ----------------------------------------------------------------------------


class ListRunsInput(BaseModel):
    status: str | None = Field(
        default=None, description="Optional status filter (running/completed/halted/error)."
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class OrchestrationListRunsTool(DataMCPTool):
    name = "data.orchestration.list_runs"
    description = (
        "Return recent workflow_runs rows. Falls back to an empty "
        "list when the Phase 5 table is not yet provisioned so the "
        "UI never crashes during the rollout window."
    )
    args_schema = ListRunsInput
    category = "orchestration"
    tags = ("orchestration", "runs", "ledger")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        status: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_workflows import WorkflowRun  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return MCPToolResult(
                ok=True,
                data={"runs": [], "table_present": False},
                rows_returned=0,
                summary="workflow_runs table not yet provisioned (Phase 5)",
            )
        try:
            with get_session() as session:
                q = session.query(WorkflowRun).order_by(WorkflowRun.started_at.desc())
                if status:
                    q = q.filter(WorkflowRun.status == status)
                rows = q.limit(int(limit)).all()
                runs = [
                    {
                        "run_id": str(getattr(r, "id", "")),
                        "workflow_spec_name": getattr(r, "workflow_spec_name", ""),
                        "status": getattr(r, "status", ""),
                        "started_at": str(getattr(r, "started_at", "") or ""),
                        "completed_at": str(getattr(r, "completed_at", "") or ""),
                        "duration_ms": float(getattr(r, "duration_ms", 0.0) or 0.0),
                        "cost_usd": float(getattr(r, "cost_usd", 0.0) or 0.0),
                    }
                    for r in rows
                ]
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"list_runs failed: {exc}", summary="query failed"
            )
        return MCPToolResult(
            ok=True,
            data={"runs": runs, "table_present": True},
            rows_returned=len(runs),
            summary=f"{len(runs)} workflow_runs row(s)",
        )


# ----------------------------------------------------------------------------
# data.orchestration.get_run
# ----------------------------------------------------------------------------


class GetRunInput(BaseModel):
    run_id: str = Field(min_length=1)


@register_data_mcp_tool
class OrchestrationGetRunTool(DataMCPTool):
    name = "data.orchestration.get_run"
    description = (
        "Return a single workflow_runs row by id with its breadcrumb "
        "trail. Returns ok=False with a 'not_found' error when the "
        "table is missing or the row doesn't exist."
    )
    args_schema = GetRunInput
    category = "orchestration"
    tags = ("orchestration", "runs", "ledger")
    required_scopes = ("data:read",)

    def run(
        self, *, ctx: MCPToolContext, run_id: str
    ) -> MCPToolResult:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_workflows import WorkflowRun  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error="workflow_runs table not yet provisioned",
                summary="table missing",
            )
        try:
            with get_session() as session:
                row = (
                    session.query(WorkflowRun)
                    .filter(WorkflowRun.id == run_id)
                    .one_or_none()
                )
                if row is None:
                    return MCPToolResult(
                        ok=False, error="not_found", summary=f"run {run_id} not found"
                    )
                data = {
                    "run_id": str(row.id),
                    "workflow_spec_name": getattr(row, "workflow_spec_name", ""),
                    "spec_version_id": getattr(row, "spec_version_id", None),
                    "status": getattr(row, "status", ""),
                    "started_at": str(getattr(row, "started_at", "") or ""),
                    "completed_at": str(getattr(row, "completed_at", "") or ""),
                    "breadcrumbs": getattr(row, "breadcrumbs", []) or [],
                    "cost_usd": float(getattr(row, "cost_usd", 0.0) or 0.0),
                    "error": getattr(row, "error", None),
                }
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=str(exc), summary="get_run failed")
        return MCPToolResult(
            ok=True, data=data, rows_returned=1, summary=f"run {run_id} fetched"
        )


# ----------------------------------------------------------------------------
# data.orchestration.list_workflows
# ----------------------------------------------------------------------------


class ListWorkflowsInput(BaseModel):
    include_yaml: bool = Field(
        default=False,
        description="When true, include every workflow YAML file discovered under configs/workflows.",
    )


@register_data_mcp_tool
class OrchestrationListWorkflowsTool(DataMCPTool):
    name = "data.orchestration.list_workflows"
    description = (
        "Return registered WorkflowSpec entries (name, adapter, "
        "annotations). Reads the in-memory registry; when "
        "include_yaml=true also enumerates configs/workflows/*.yaml."
    )
    args_schema = ListWorkflowsInput
    category = "orchestration"
    tags = ("orchestration", "workflows", "catalog")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        include_yaml: bool = False,
    ) -> MCPToolResult:
        out: list[dict[str, Any]] = []
        try:
            from aqp.agents.orchestration.registry_specs import list_workflow_specs

            for spec in list_workflow_specs():
                out.append(
                    {
                        "name": spec.name,
                        "adapter": spec.adapter,
                        "description": spec.description,
                        "max_rounds": spec.max_rounds,
                        "annotations": list(spec.annotations or []),
                        "source": "registry",
                    }
                )
        except Exception:  # noqa: BLE001 - Phase 5 registry not yet shipped
            logger.debug("workflow registry not yet available", exc_info=True)

        if include_yaml:
            from pathlib import Path

            from aqp.agents.orchestration.spec import load_workflow_specs_from_dir

            for candidate in (
                Path("configs/workflows"),
                Path("aqp/configs/workflows"),
            ):
                if candidate.exists():
                    for spec in load_workflow_specs_from_dir(str(candidate)):
                        out.append(
                            {
                                "name": spec.name,
                                "adapter": spec.adapter,
                                "description": spec.description,
                                "max_rounds": spec.max_rounds,
                                "annotations": list(spec.annotations or []),
                                "source": "yaml",
                                "yaml_dir": str(candidate),
                            }
                        )
                    break

        return MCPToolResult(
            ok=True,
            data={"workflows": out},
            rows_returned=len(out),
            summary=f"{len(out)} workflow(s) discovered",
        )


# ----------------------------------------------------------------------------
# data.orchestration.fusion_inputs_for_run
# ----------------------------------------------------------------------------


class FusionInputsInput(BaseModel):
    run_id: str = Field(min_length=1)


@register_data_mcp_tool
class OrchestrationFusionInputsTool(DataMCPTool):
    name = "data.orchestration.fusion_inputs_for_run"
    description = (
        "Return the Phase 4 fusion-input snapshot (quant signals, "
        "debate verdict, model predictions, risk overlay) for a "
        "specific workflow run. Read-only audit hook."
    )
    args_schema = FusionInputsInput
    category = "orchestration"
    tags = ("orchestration", "fusion", "audit")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, run_id: str) -> MCPToolResult:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_workflows import WorkflowRun  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return MCPToolResult(
                ok=True,
                data={"fusion_inputs": {}, "table_present": False},
                summary="workflow_runs table not yet provisioned",
            )
        try:
            with get_session() as session:
                row = (
                    session.query(WorkflowRun)
                    .filter(WorkflowRun.id == run_id)
                    .one_or_none()
                )
                if row is None:
                    return MCPToolResult(
                        ok=False, error="not_found", summary=f"run {run_id} not found"
                    )
                state = getattr(row, "final_state", None) or {}
                fusion_inputs = (state or {}).get("fusion_inputs") or {}
                fusion_output = (state or {}).get("fusion_output") or {}
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=str(exc), summary="lookup failed")
        return MCPToolResult(
            ok=True,
            data={
                "run_id": run_id,
                "fusion_inputs": fusion_inputs,
                "fusion_output": fusion_output,
            },
            summary=f"fusion snapshot for run {run_id}",
        )


# ----------------------------------------------------------------------------
# data.orchestration.health
# ----------------------------------------------------------------------------


@register_data_mcp_tool
class OrchestrationHealthTool(DataMCPTool):
    name = "data.orchestration.health"
    description = (
        "Read-only snapshot of the workflow-run watchdog — running / "
        "pending / halted_last_24h counts plus the stalled-candidate "
        "list. Companion to data.agents.health for the Phase 6 halt "
        "fan-out. Use before deciding to call /workflows/halt."
    )
    args_schema = _NoArgs
    category = "orchestration"
    tags = ("orchestration", "health", "watchdog")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, **_: object) -> MCPToolResult:
        try:
            from aqp.tasks.agent_watchdog_tasks import (
                collect_workflow_health_snapshot,
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"workflow watchdog unavailable: {exc}",
                summary="watchdog unavailable",
            )
        try:
            snap = collect_workflow_health_snapshot()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=str(exc), summary="health failed"
            )
        return MCPToolResult(
            ok=True,
            data=snap,
            rows_returned=len(snap.get("stalled_candidates", [])),
            summary=(
                f"running={snap['running']} pending={snap['pending']} "
                f"halted_24h={snap['halted_last_24h']} "
                f"stalled={len(snap['stalled_candidates'])}"
            ),
        )


__all__: list[str] = []
