"""QuestDB time-series DataMCP tools.

Phase 2b of the AQP infra-expansion plan exposes QuestDB to agents
via four tools:

- ``data.timeseries.questdb.list_tables`` — discovery.
- ``data.timeseries.questdb.partition_info`` — partition rowcount +
  min/max timestamp for a single table.
- ``data.timeseries.questdb.sample_by`` — SAMPLE BY downsampling for
  trailing windows (rolling VWAP, 1m / 5m bars).
- ``data.timeseries.questdb.ilp_send`` — write a small batch via ILP
  (developer-only path; production ingest goes via Redpanda Connect).

Reads enforce a strict allow-list of tables to avoid agent prompt-
injection picking up arbitrary internal QuestDB schemas. The list is
sourced from the topology service entry for QuestDB plus the
``questdb`` dataset kind catalog rows.
"""
from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


# Allow-listed tables. Phase 2 ships with the canonical market data
# tables that the topology declares; new tables get added here when
# their dataset kind catalog entry registers.
_ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "market_l1",
        "market_l2",
        "executions",
        "agentic_state",
        "ohlcv_1m",
        "ohlcv_5m",
        "ohlcv_15m",
        "ohlcv_1h",
        "ohlcv_1d",
    }
)


def _check_table(table: str) -> str:
    if table not in _ALLOWED_TABLES:
        raise ValueError(
            f"questdb table {table!r} is not in the MCP allow-list; "
            f"available: {sorted(_ALLOWED_TABLES)}"
        )
    return table


class ListQuestDBTablesInput(BaseModel):
    pass


@register_data_mcp_tool
class ListQuestDBTablesTool(DataMCPTool):
    name = "data.timeseries.questdb.list_tables"
    description = "List QuestDB tables with row counts + partition strategy."
    args_schema = ListQuestDBTablesInput
    category = "timeseries"
    tags = ("questdb", "timeseries")

    def run(self, *, ctx: MCPToolContext) -> MCPToolResult:
        try:
            rows = asyncio.run(_list_tables())
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"questdb list_tables failed: {exc}")
        return MCPToolResult(
            ok=True,
            data=rows,
            rows_returned=len(rows),
            summary=f"QuestDB has {len(rows)} tables",
        )


class PartitionInfoInput(BaseModel):
    table: str = Field(..., description="Table name (must be in the MCP allow-list).")


@register_data_mcp_tool
class PartitionInfoTool(DataMCPTool):
    name = "data.timeseries.questdb.partition_info"
    description = "Per-partition rowcount + min/max timestamp for a QuestDB table."
    args_schema = PartitionInfoInput
    category = "timeseries"
    tags = ("questdb", "timeseries")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        table: str,
    ) -> MCPToolResult:
        try:
            allowed = _check_table(table)
            rows = asyncio.run(_partition_info(allowed))
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"questdb partition_info: {exc}")
        return MCPToolResult(
            ok=True,
            data=rows,
            rows_returned=len(rows),
            summary=f"{table}: {len(rows)} partitions",
        )


class SampleByInput(BaseModel):
    table: str = Field(..., description="Table name (allow-list required).")
    ts_column: str = Field(default="ts")
    bucket: str = Field(default="1m", description="QuestDB SAMPLE BY bucket (e.g., 1m, 5m, 1h).")
    columns: list[str] = Field(
        default_factory=list,
        description="Aggregate columns. Empty -> SELECT *.",
    )
    where: str | None = Field(default=None, description="Optional WHERE clause body.")
    limit: int = Field(default=1000, ge=1, le=100_000)


@register_data_mcp_tool
class SampleByTool(DataMCPTool):
    name = "data.timeseries.questdb.sample_by"
    description = (
        "Run a QuestDB SAMPLE BY downsampling query. Used by agents for "
        "trailing-window calculations (rolling VWAP, 1m/5m OHLCV bars)."
    )
    args_schema = SampleByInput
    category = "timeseries"
    tags = ("questdb", "timeseries", "downsample")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        table: str,
        ts_column: str = "ts",
        bucket: str = "1m",
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int = 1000,
    ) -> MCPToolResult:
        try:
            allowed = _check_table(table)
            rows = asyncio.run(
                _sample_by(
                    table=allowed,
                    ts_column=ts_column,
                    bucket=bucket,
                    columns=list(columns or []),
                    where=where,
                    limit=int(limit),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"questdb sample_by: {exc}")
        return MCPToolResult(
            ok=True,
            data=rows,
            rows_returned=len(rows),
            summary=f"{table} SAMPLE BY {bucket}: {len(rows)} rows",
        )


class IlpSendInput(BaseModel):
    measurement: str
    rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Records with tag_keys + field_keys + ts_ns.",
    )
    tag_keys: list[str] = Field(default_factory=list)
    field_keys: list[str] = Field(default_factory=list)


@register_data_mcp_tool
class IlpSendTool(DataMCPTool):
    name = "data.timeseries.questdb.ilp_send"
    description = (
        "Developer-only QuestDB ILP write. Production ingest flows through "
        "Redpanda Connect's QuestDB sink; use this tool for sandbox / smoke "
        "tests only."
    )
    args_schema = IlpSendInput
    category = "timeseries"
    tags = ("questdb", "timeseries", "ingest")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        measurement: str,
        rows: list[dict[str, Any]] | None = None,
        tag_keys: list[str] | None = None,
        field_keys: list[str] | None = None,
    ) -> MCPToolResult:
        from aqp.data.timeseries.questdb_ingest import QuestDBIngester

        try:
            allowed = _check_table(measurement)
            ingester = QuestDBIngester()
            try:
                bytes_written = ingester.send_batch(
                    allowed,
                    records=list(rows or []),
                    tag_keys=list(tag_keys or []),
                    field_keys=list(field_keys or []),
                )
            finally:
                ingester.close()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"questdb ilp_send: {exc}")
        return MCPToolResult(
            ok=True,
            data={"measurement": measurement, "bytes_written": int(bytes_written)},
            summary=f"ILP wrote {bytes_written} bytes to {measurement}",
        )


# ---- async helpers ----------------------------------------------------------


async def _list_tables() -> list[dict[str, Any]]:
    from aqp.data.timeseries.questdb_client import get_questdb_client

    client = await get_questdb_client()
    return await client.list_tables()


async def _partition_info(table: str) -> list[dict[str, Any]]:
    from aqp.data.timeseries.questdb_client import get_questdb_client

    client = await get_questdb_client()
    return await client.partition_info(table)


async def _sample_by(
    *,
    table: str,
    ts_column: str,
    bucket: str,
    columns: list[str],
    where: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    from aqp.data.timeseries.questdb_client import get_questdb_client

    client = await get_questdb_client()
    return await client.sample_by(
        table=table,
        ts_column=ts_column,
        bucket=bucket,
        agg_columns=columns,
        where=where,
        limit=limit,
    )


__all__ = [
    "IlpSendTool",
    "ListQuestDBTablesTool",
    "PartitionInfoTool",
    "SampleByTool",
]
