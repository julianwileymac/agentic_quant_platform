"""Streaming (Kafka / Flink / producers) DataMCP tools."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


class ListKafkaTopicsInput(BaseModel):
    pattern: str | None = None


@register_data_mcp_tool
class ListKafkaTopicsTool(DataMCPTool):
    name = "data.streaming.kafka.list_topics"
    description = "List Kafka topics via NativeKafkaAdmin (or cluster_mgmt fallback)."
    args_schema = ListKafkaTopicsInput
    category = "streaming"
    tags = ("streaming", "kafka")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        pattern: str | None = None,
    ) -> MCPToolResult:
        try:
            from aqp.streaming.admin.kafka_admin import NativeKafkaAdmin

            admin = NativeKafkaAdmin()
            topics = admin.list_topics()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"kafka admin unavailable: {exc}")
        if pattern:
            import re

            try:
                rx = re.compile(pattern)
                topics = [t for t in topics if rx.search(getattr(t, "name", str(t)))]
            except re.error as exc:  # noqa: BLE001
                return MCPToolResult(ok=False, error=f"invalid pattern: {exc}")
        data = [
            getattr(t, "to_dict", lambda: {"name": str(t)})()
            for t in topics
        ]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"listed {len(data)} kafka topics",
        )


class ListFlinkJobsInput(BaseModel):
    pass


@register_data_mcp_tool
class ListFlinkJobsTool(DataMCPTool):
    name = "data.streaming.flink.list_jobs"
    description = "List Flink jobs via the FlinkRestClient (or cluster_mgmt fallback)."
    args_schema = ListFlinkJobsInput
    category = "streaming"
    tags = ("streaming", "flink")

    def run(self, *, ctx: MCPToolContext) -> MCPToolResult:
        try:
            from aqp.streaming.admin.flink_admin import FlinkRestClient

            client = FlinkRestClient()
            jobs = client.jobs_overview()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"flink rest unavailable: {exc}")
        data = [
            getattr(j, "to_dict", lambda: {"id": str(j)})()
            for j in jobs
        ]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"listed {len(data)} flink jobs",
        )


class ListProducersInput(BaseModel):
    enabled_only: bool = False


@register_data_mcp_tool
class ListProducersTool(DataMCPTool):
    name = "data.streaming.producers.list"
    description = "List MarketDataProducerRow entries via ProducerSupervisor."
    args_schema = ListProducersInput
    category = "streaming"
    tags = ("streaming", "producers")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        enabled_only: bool = False,
    ) -> MCPToolResult:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_producers import MarketDataProducerRow

        with get_session() as session:
            query = select(MarketDataProducerRow)
            if enabled_only:
                query = query.where(MarketDataProducerRow.enabled.is_(True))
            rows = session.execute(query).scalars().all()
            data = [
                {
                    "id": row.id,
                    "name": row.name,
                    "kind": getattr(row, "kind", None),
                    "topics": list(getattr(row, "topics", []) or []),
                    "runtime": getattr(row, "runtime", None),
                    "desired_replicas": int(getattr(row, "desired_replicas", 0) or 0),
                    "current_replicas": int(getattr(row, "current_replicas", 0) or 0),
                    "enabled": bool(getattr(row, "enabled", True)),
                    "last_status": getattr(row, "last_status", None),
                }
                for row in rows
            ]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"listed {len(data)} producers",
        )


__all__ = [
    "ListFlinkJobsTool",
    "ListKafkaTopicsTool",
    "ListProducersTool",
]
