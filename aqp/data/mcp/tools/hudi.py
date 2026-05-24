"""Apache Hudi DataMCP tools (additive lakehouse).

Phase 2e of the AQP infra-expansion plan. Five tools:

- ``data.lakehouse.hudi.list_tables`` — discovery via Hive sync.
- ``data.lakehouse.hudi.upsert_arrow`` — write a small Arrow batch
  through the canonical :class:`HudiWriter` (developer-only path;
  production upserts run via HoodieStreamer).
- ``data.lakehouse.hudi.run_compaction`` — submit a compaction
  SparkApplication (Hudi only — Iceberg compaction goes through its
  own MCP tools).
- ``data.lakehouse.hudi.run_clustering`` — submit a clustering
  SparkApplication.
- ``data.lakehouse.hudi.start_streamer`` / ``stop_streamer`` —
  HoodieStreamer lifecycle (Kafka -> Hudi continuous ingestion).

Iceberg remains the canonical lakehouse write path (rule 3); the
Hudi tools NEVER write to ``aqp_bronze_*`` / ``aqp_silver_*`` /
``aqp_gold_*`` namespaces. The :func:`assert_not_iceberg` guard in
:mod:`aqp.data.lakehouse.hudi.namespaces` enforces this at every
write entry-point.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.lakehouse.hudi.namespaces import (
    DEFAULT_HUDI_PREFIX,
    hudi_namespace,
)
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


class ListTablesInput(BaseModel):
    pattern: str | None = None


@register_data_mcp_tool
class HudiListTablesTool(DataMCPTool):
    name = "data.lakehouse.hudi.list_tables"
    description = (
        "List Hudi tables registered in the Hive sync (separate from the "
        "Iceberg catalog). Returns name + namespace + table-type + last "
        "compaction timestamp."
    )
    args_schema = ListTablesInput
    category = "lakehouse"
    tags = ("hudi", "lakehouse")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        pattern: str | None = None,
    ) -> MCPToolResult:
        # Hive sync metadata lookup goes through Polaris (the AQP-side
        # Iceberg + Hudi metastore) when available; for environments
        # without Polaris running, return an explicit "unavailable"
        # rather than a partial list.
        try:
            from aqp.services.polaris_client import PolarisClient

            client = PolarisClient()
            namespaces = [
                ns for ns in client.list_namespaces()
                if str(ns).startswith(DEFAULT_HUDI_PREFIX)
            ]
            tables: list[dict[str, Any]] = []
            for ns in namespaces:
                for tbl in client.list_tables(ns):
                    tables.append({"namespace": str(ns), "name": str(tbl)})
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"hudi list_tables (via polaris): {exc}",
            )
        if pattern:
            import re

            try:
                rx = re.compile(pattern)
                tables = [t for t in tables if rx.search(t["name"])]
            except re.error as exc:
                return MCPToolResult(ok=False, error=f"invalid pattern: {exc}")
        return MCPToolResult(
            ok=True,
            data=tables,
            rows_returned=len(tables),
            summary=f"hudi tables: {len(tables)}",
        )


class UpsertArrowInput(BaseModel):
    namespace: str
    table: str
    record_key_field: str
    precombine_field: str
    rows: list[dict[str, Any]]
    partition_path_field: str = ""
    table_type: str = Field(default="MERGE_ON_READ")
    operation: str = Field(default="upsert")


@register_data_mcp_tool
class HudiUpsertArrowTool(DataMCPTool):
    name = "data.lakehouse.hudi.upsert_arrow"
    description = (
        "Developer-only Hudi upsert. Production upserts flow through "
        "HoodieStreamer (started by data.lakehouse.hudi.start_streamer); "
        "this tool exists for sandbox / smoke tests."
    )
    args_schema = UpsertArrowInput
    category = "lakehouse"
    tags = ("hudi", "lakehouse", "ingest")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        table: str,
        record_key_field: str,
        precombine_field: str,
        rows: list[dict[str, Any]],
        partition_path_field: str = "",
        table_type: str = "MERGE_ON_READ",
        operation: str = "upsert",
    ) -> MCPToolResult:
        from aqp.data.lakehouse.hudi.hudi_writer import (
            HudiWriter,
            HudiWriteSpec,
        )

        try:
            spec = HudiWriteSpec(
                namespace=namespace,
                table=table,
                record_key_field=record_key_field,
                precombine_field=precombine_field,
                partition_path_field=partition_path_field,
                table_type=table_type,
                operation=operation,
            )
            writer = HudiWriter(spec)
            result = writer.write(rows)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"hudi upsert: {exc}")
        return MCPToolResult(
            ok=True,
            data=result,
            rows_returned=len(rows),
            summary=f"hudi upsert {hudi_namespace(namespace)}/{table}: {len(rows)} rows",
        )


class StartStreamerInput(BaseModel):
    name: str
    namespace: str
    table: str
    kafka_topic: str
    record_key_field: str = Field(default="vt_symbol")
    precombine_field: str = Field(default="ts_ns")
    partition_path_field: str = Field(default="exchange,date_str")
    source_class: str = Field(
        default="org.apache.hudi.utilities.sources.AvroKafkaSource"
    )


@register_data_mcp_tool
class HudiStartStreamerTool(DataMCPTool):
    name = "data.lakehouse.hudi.start_streamer"
    description = (
        "Submit a continuous HoodieStreamer SparkApplication for "
        "Kafka -> Hudi ingestion."
    )
    args_schema = StartStreamerInput
    category = "lakehouse"
    tags = ("hudi", "lakehouse", "streaming")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        name: str,
        namespace: str,
        table: str,
        kafka_topic: str,
        record_key_field: str = "vt_symbol",
        precombine_field: str = "ts_ns",
        partition_path_field: str = "exchange,date_str",
        source_class: str = "org.apache.hudi.utilities.sources.AvroKafkaSource",
    ) -> MCPToolResult:
        from aqp.data.lakehouse.hudi.hudi_streamer import (
            HudiStreamerLauncher,
            HudiStreamerSpec,
        )

        try:
            spec = HudiStreamerSpec(
                name=name,
                namespace=namespace,
                table=table,
                source_class=source_class,
                record_key_field=record_key_field,
                precombine_field=precombine_field,
                partition_path_field=partition_path_field,
                kafka_topic=kafka_topic,
            )
            launcher = HudiStreamerLauncher()
            payload = launcher.start(spec)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"hudi start_streamer: {exc}")
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"started HudiStreamer {name}",
        )


class StopStreamerInput(BaseModel):
    name: str
    namespace: str = Field(default="aqp-mlops")


@register_data_mcp_tool
class HudiStopStreamerTool(DataMCPTool):
    name = "data.lakehouse.hudi.stop_streamer"
    description = "Delete a HoodieStreamer SparkApplication."
    args_schema = StopStreamerInput
    category = "lakehouse"
    tags = ("hudi", "lakehouse", "streaming")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        name: str,
        namespace: str = "aqp-mlops",
    ) -> MCPToolResult:
        from aqp.data.lakehouse.hudi.hudi_streamer import HudiStreamerLauncher

        try:
            payload = HudiStreamerLauncher().stop(name, namespace=namespace)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"hudi stop_streamer: {exc}")
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"stopped HudiStreamer {name}",
        )


__all__ = [
    "HudiListTablesTool",
    "HudiStartStreamerTool",
    "HudiStopStreamerTool",
    "HudiUpsertArrowTool",
]
