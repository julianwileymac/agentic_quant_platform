"""``data.automation.*`` DataMCP tools.

Read-only surface over the Celery beat schedule entries the Phase 3
:class:`AutomationScheduleAdapter` registers. Lets agents enumerate
the scheduled workflow runs without poking at the Celery configuration
directly.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


_BEAT_PREFIXES = ("workflow-", "orchestration-")
"""Beat-schedule entry prefixes the orchestration scheduler claims.

Both prefixes are honoured so existing operator runbooks (which may
use ``orchestration-foo`` keys) keep working when the
:class:`AutomationScheduleAdapter` lands.
"""


class _NoArgs(BaseModel):
    """No arguments — full snapshot."""


@register_data_mcp_tool
class AutomationListSchedulesTool(DataMCPTool):
    name = "data.automation.list_schedules"
    description = (
        "Enumerate every Celery beat entry whose key starts with "
        "'workflow-' or 'orchestration-' (the prefixes the Phase 3 "
        "AutomationScheduleAdapter claims). Read-only."
    )
    args_schema = _NoArgs
    category = "orchestration"
    tags = ("orchestration", "schedule", "celery_beat")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, **_: object) -> MCPToolResult:
        try:
            from aqp.tasks.celery_app import celery_app
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"celery_app unavailable: {exc}",
                summary="celery import failed",
            )
        beat = dict(getattr(celery_app.conf, "beat_schedule", {}) or {})
        out: list[dict[str, Any]] = []
        for key, entry in sorted(beat.items()):
            if not key.startswith(_BEAT_PREFIXES):
                continue
            schedule = entry.get("schedule") if isinstance(entry, dict) else None
            schedule_repr: Any = (
                float(schedule)
                if isinstance(schedule, (int, float))
                else repr(schedule)
            )
            out.append(
                {
                    "key": key,
                    "task": entry.get("task") if isinstance(entry, dict) else None,
                    "schedule": schedule_repr,
                    "args": entry.get("args") if isinstance(entry, dict) else None,
                    "kwargs": entry.get("kwargs") if isinstance(entry, dict) else None,
                }
            )
        return MCPToolResult(
            ok=True,
            data={"schedules": out},
            rows_returned=len(out),
            summary=f"{len(out)} orchestration schedule(s) active",
        )


class GetScheduleStatusInput(BaseModel):
    key: str = Field(
        min_length=1,
        description=(
            "Celery beat entry key (e.g. 'workflow-daily-stock-analysis'). "
            "Must start with one of the orchestration prefixes."
        ),
    )


@register_data_mcp_tool
class AutomationGetScheduleStatusTool(DataMCPTool):
    name = "data.automation.get_schedule_status"
    description = (
        "Return the registration record + last-run / next-run info "
        "for one orchestration beat entry. Returns ok=False with "
        "'not_found' for unknown keys."
    )
    args_schema = GetScheduleStatusInput
    category = "orchestration"
    tags = ("orchestration", "schedule", "celery_beat")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, key: str) -> MCPToolResult:
        if not key.startswith(_BEAT_PREFIXES):
            return MCPToolResult(
                ok=False,
                error=(
                    "invalid key prefix: key must start with 'workflow-' "
                    "or 'orchestration-'"
                ),
                summary="invalid key prefix",
            )
        try:
            from aqp.tasks.celery_app import celery_app
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"celery_app unavailable: {exc}",
                summary="celery import failed",
            )
        beat = dict(getattr(celery_app.conf, "beat_schedule", {}) or {})
        entry = beat.get(key)
        if entry is None:
            return MCPToolResult(
                ok=False, error="not_found", summary=f"no beat entry {key!r}"
            )
        snapshot = {
            "key": key,
            "task": entry.get("task") if isinstance(entry, dict) else None,
            "schedule": (
                float(entry["schedule"])
                if isinstance(entry, dict)
                and isinstance(entry.get("schedule"), (int, float))
                else repr(entry.get("schedule") if isinstance(entry, dict) else entry)
            ),
            "args": entry.get("args") if isinstance(entry, dict) else None,
            "kwargs": entry.get("kwargs") if isinstance(entry, dict) else None,
        }
        return MCPToolResult(ok=True, data=snapshot, summary=f"{key} status")


__all__: list[str] = []
