"""Iceberg DataMCP tools — bounded read access to raw tables.

All read tools enforce workspace tenancy via :func:`_workspace_filter_clause`.
The filter is appended to any caller-supplied ``row_filter`` so tables
written with ``shared=False`` (the default) only return rows whose
``_workspace_id`` matches the active context, plus rows that pre-date
the tenancy stamping (``_workspace_id IS NULL``).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_data_minimization
from aqp.data.mcp.registry import register_data_mcp_tool


def _workspace_filter_clause(ctx: MCPToolContext) -> str | None:
    """Return an Iceberg expression string scoping reads to the workspace.

    Combined with the user's optional ``row_filter`` via ``AND``. Returns
    ``None`` when the table has no tenancy column to filter on (yet) —
    those calls fall through to the snapshot-historic filter alone.
    """
    if not ctx.workspace_id:
        return None
    return f"(_workspace_id == '{ctx.workspace_id}') OR (_workspace_id == None)"


def _compose_row_filter(user_filter: str | None, tenancy_filter: str | None) -> str | None:
    """Combine the user's row_filter with the tenancy filter via AND."""
    parts = [p for p in (user_filter, tenancy_filter) if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return " AND ".join(f"({p})" for p in parts)


class ReadIcebergSliceInput(BaseModel):
    iceberg_identifier: str = Field(...)
    columns: list[str] | None = None
    limit: int = Field(default=100, ge=1, le=2000)
    row_filter: str | None = Field(
        default=None,
        description="Optional Iceberg expression string (eg. \"vt_symbol == 'AAPL.NASDAQ'\").",
    )


@register_data_mcp_tool
class ReadIcebergSliceTool(DataMCPTool):
    name = "data.iceberg.read_slice"
    description = (
        "Read a bounded slice of an Iceberg table. Always returns at most "
        "`limit` rows. Use `columns` to project — leaving it empty returns "
        "all non-PII columns."
    )
    args_schema = ReadIcebergSliceInput
    category = "iceberg"
    tags = ("iceberg", "read")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        iceberg_identifier: str,
        columns: list[str] | None = None,
        limit: int = 100,
        row_filter: str | None = None,
    ) -> MCPToolResult:
        try:
            from aqp.data.iceberg_catalog import read_arrow

            effective_filter = _compose_row_filter(row_filter, _workspace_filter_clause(ctx))
            try:
                arrow_tbl = read_arrow(
                    iceberg_identifier,
                    columns=tuple(columns) if columns else None,
                    limit=int(limit),
                    row_filter=effective_filter,
                )
            except Exception:
                # Tables that pre-date the tenancy refactor don't have a
                # ``_workspace_id`` column at all, so PyIceberg raises on
                # the predicate. Fall back to the user's filter alone.
                if effective_filter != row_filter:
                    arrow_tbl = read_arrow(
                        iceberg_identifier,
                        columns=tuple(columns) if columns else None,
                        limit=int(limit),
                        row_filter=row_filter,
                    )
                else:
                    raise
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"read_arrow failed: {exc}")
        if arrow_tbl is None:
            return MCPToolResult(ok=False, error=f"table {iceberg_identifier!r} not found")
        rows = arrow_tbl.to_pylist()
        return MCPToolResult(
            ok=True,
            data={"rows": rows, "schema": [str(f) for f in arrow_tbl.schema]},
            rows_returned=len(rows),
            summary=f"read {len(rows)} rows from {iceberg_identifier}",
        )


class IcebergSnapshotHistoryInput(BaseModel):
    iceberg_identifier: str = Field(...)


@register_data_mcp_tool
class IcebergSnapshotHistoryTool(DataMCPTool):
    name = "data.iceberg.snapshot_history"
    description = "Return the snapshot history of an Iceberg table (oldest -> newest)."
    args_schema = IcebergSnapshotHistoryInput
    category = "iceberg"
    tags = ("iceberg", "history")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        iceberg_identifier: str,
    ) -> MCPToolResult:
        try:
            from aqp.data.iceberg_catalog import snapshot_history

            data = snapshot_history(iceberg_identifier)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"snapshot_history failed: {exc}")
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"snapshot history for {iceberg_identifier}",
        )


class IcebergTimeTravelReadInput(BaseModel):
    iceberg_identifier: str = Field(...)
    snapshot_id: int | None = None
    as_of_iso: str | None = Field(
        default=None,
        description="ISO 8601 datetime; reads the latest snapshot at or before this time.",
    )
    columns: list[str] | None = None
    limit: int = Field(default=100, ge=1, le=2000)


@register_data_mcp_tool
class IcebergTimeTravelReadTool(DataMCPTool):
    name = "data.iceberg.time_travel_read"
    description = (
        "Time-travel read against an Iceberg table — pin to a specific "
        "snapshot_id or read at a historical as_of timestamp to defeat "
        "lookahead bias in backtests."
    )
    args_schema = IcebergTimeTravelReadInput
    category = "iceberg"
    tags = ("iceberg", "time-travel")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        iceberg_identifier: str,
        snapshot_id: int | None = None,
        as_of_iso: str | None = None,
        columns: list[str] | None = None,
        limit: int = 100,
    ) -> MCPToolResult:
        try:
            from aqp.data.iceberg_catalog import read_arrow_at

            as_of_dt: datetime | None = None
            if as_of_iso:
                try:
                    as_of_dt = datetime.fromisoformat(as_of_iso)
                except ValueError as exc:
                    return MCPToolResult(
                        ok=False, error=f"invalid as_of_iso: {exc}"
                    )
            arrow_tbl = read_arrow_at(
                iceberg_identifier,
                snapshot_id=snapshot_id,
                as_of=as_of_dt,
                columns=tuple(columns) if columns else None,
                limit=int(limit),
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"read_arrow_at failed: {exc}")
        if arrow_tbl is None:
            return MCPToolResult(ok=False, error=f"table {iceberg_identifier!r} not found")
        rows = arrow_tbl.to_pylist()
        return MCPToolResult(
            ok=True,
            data={
                "rows": rows,
                "schema": [str(f) for f in arrow_tbl.schema],
                "snapshot_id": snapshot_id,
                "as_of": as_of_iso,
            },
            rows_returned=len(rows),
            summary=(
                f"time-travel read {len(rows)} rows from {iceberg_identifier} "
                f"(snapshot_id={snapshot_id}, as_of={as_of_iso})"
            ),
        )


__all__ = [
    "IcebergSnapshotHistoryTool",
    "IcebergTimeTravelReadTool",
    "ReadIcebergSliceTool",
]
