"""Streaming (Kafka / Redpanda / Flink / producers / cluster registry) DataMCP tools.

Phase 2a of the AQP infra-expansion plan added side-by-side Redpanda
support. The ``data.streaming.kafka.*`` namespace defaults to the
existing Strimzi cluster; ``data.streaming.redpanda.*`` targets the
new Redpanda cluster; ``data.streaming.clusters.*`` reads the
in-process :mod:`aqp.streaming.clusters` registry.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


def _list_topics(cluster: str | None, pattern: str | None) -> MCPToolResult:
    """Shared topic-list implementation used by both Strimzi + Redpanda tools."""
    try:
        from aqp.streaming.admin.kafka_admin import NativeKafkaAdmin

        admin = NativeKafkaAdmin(cluster=cluster) if cluster else NativeKafkaAdmin()
        topics = admin.list_topics()
    except Exception as exc:  # noqa: BLE001
        return MCPToolResult(
            ok=False,
            error=f"streaming admin unavailable for cluster={cluster!r}: {exc}",
        )
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
    cluster_label = cluster or "strimzi"
    return MCPToolResult(
        ok=True,
        data=data,
        rows_returned=len(data),
        summary=f"listed {len(data)} topics on cluster={cluster_label}",
    )


class ListKafkaTopicsInput(BaseModel):
    pattern: str | None = None


@register_data_mcp_tool
class ListKafkaTopicsTool(DataMCPTool):
    name = "data.streaming.kafka.list_topics"
    description = "List Kafka topics on the Strimzi cluster (legacy default)."
    args_schema = ListKafkaTopicsInput
    category = "streaming"
    tags = ("streaming", "kafka", "strimzi")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        pattern: str | None = None,
    ) -> MCPToolResult:
        return _list_topics(cluster="strimzi", pattern=pattern)


class ListRedpandaTopicsInput(BaseModel):
    pattern: str | None = None


@register_data_mcp_tool
class ListRedpandaTopicsTool(DataMCPTool):
    name = "data.streaming.redpanda.list_topics"
    description = (
        "List Kafka-API topics on the Redpanda cluster. Side-by-side with "
        "data.streaming.kafka.list_topics; topic-prefix routing in "
        "aqp.streaming.clusters decides which cluster a given topic lives on."
    )
    args_schema = ListRedpandaTopicsInput
    category = "streaming"
    tags = ("streaming", "redpanda")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        pattern: str | None = None,
    ) -> MCPToolResult:
        return _list_topics(cluster="redpanda", pattern=pattern)


class ResolveClusterInput(BaseModel):
    topic: str = Field(..., description="Topic name to look up in the route table.")


@register_data_mcp_tool
class ResolveClusterTool(DataMCPTool):
    name = "data.streaming.clusters.resolve"
    description = (
        "Return the cluster alias that owns the given topic per the topic-prefix "
        "registry in aqp.streaming.clusters. Used by agents to verify which "
        "cluster a market.l1.* / market.l2.* / execution.orders.* topic routes to."
    )
    args_schema = ResolveClusterInput
    category = "streaming"
    tags = ("streaming", "topology")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        topic: str,
    ) -> MCPToolResult:
        try:
            from aqp.streaming.clusters import cluster_for_topic

            cluster = cluster_for_topic(topic)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"cluster resolution failed: {exc}")
        return MCPToolResult(
            ok=True,
            data={
                "topic": topic,
                "cluster": cluster.name,
                "bootstrap": cluster.bootstrap,
                "schema_registry_url": cluster.schema_registry_url,
                "label": cluster.label,
            },
            summary=f"topic={topic} -> cluster={cluster.name}",
        )


class ListClustersInput(BaseModel):
    pass


@register_data_mcp_tool
class ListClustersTool(DataMCPTool):
    name = "data.streaming.clusters.list"
    description = (
        "List every registered streaming cluster (Strimzi + Redpanda) "
        "with bootstrap, schema registry, and namespace metadata. Used by the "
        "frontend admin streaming pages and by agent flows that need to "
        "compare cluster availability."
    )
    args_schema = ListClustersInput
    category = "streaming"
    tags = ("streaming", "topology")

    def run(self, *, ctx: MCPToolContext) -> MCPToolResult:
        try:
            from aqp.streaming.clusters import list_clusters

            clusters = list_clusters()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"cluster registry unavailable: {exc}")
        data: list[dict[str, Any]] = [
            {
                "name": cluster.name,
                "label": cluster.label,
                "bootstrap": cluster.bootstrap,
                "admin_bootstrap": cluster.admin_bootstrap,
                "schema_registry_url": cluster.schema_registry_url,
                "namespace": cluster.namespace,
                "security_protocol": cluster.security_protocol,
            }
            for cluster in clusters
        ]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"registered streaming clusters: {[c['name'] for c in data]}",
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
    "ListClustersTool",
    "ListFlinkJobsTool",
    "ListKafkaTopicsTool",
    "ListProducersTool",
    "ListRedpandaTopicsTool",
    "ResolveClusterTool",
]
