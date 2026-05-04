"""``/streaming/kafka`` REST surface.

Native Kafka admin operations backed by
:class:`aqp.streaming.admin.NativeKafkaAdmin` and
:class:`aqp.streaming.admin.ApicurioSchemaRegistry`. Falls back to
the cluster-mgmt proxy at ``/cluster-mgmt/kafka/*`` when native
credentials are absent.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from aqp.streaming.admin import (
    KafkaAdminError,
    KafkaAdminUnavailableError,
    get_kafka_admin,
    get_schema_registry,
)
from aqp.streaming.admin.schema_registry import SchemaRegistryError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/streaming/kafka", tags=["streaming"])


class TopicView(BaseModel):
    name: str
    partitions: int
    replication_factor: int
    config: dict[str, str] = Field(default_factory=dict)
    is_internal: bool = False


class CreateTopicRequest(BaseModel):
    name: str
    partitions: int = 1
    replication_factor: int = 1
    config: dict[str, str] = Field(default_factory=dict)


class ConsumerGroupView(BaseModel):
    group_id: str
    state: str
    members: int
    topics: list[str] = Field(default_factory=list)


class ConsumerLagPartition(BaseModel):
    topic: str
    partition: int
    low: int
    high: int
    committed: int
    lag: int


class ConsumerLagView(BaseModel):
    group_id: str
    partitions: list[ConsumerLagPartition] = Field(default_factory=list)


class TopicSampleMessage(BaseModel):
    topic: str
    partition: int
    offset: int
    timestamp: int | None = None
    key: str | None = None
    value_preview: str | None = None


class ProduceRequest(BaseModel):
    key: str | None = None
    value: dict[str, Any] = Field(default_factory=dict)


class SchemaSubjectView(BaseModel):
    subject: str


class SchemaVersionView(BaseModel):
    subject: str
    id: int | None = None
    version: int | None = None
    schema: str | None = None
    schema_type: str = "AVRO"


class RegisterSchemaRequest(BaseModel):
    schema: str
    schema_type: str = "AVRO"
    references: list[dict[str, Any]] = Field(default_factory=list)


def _native_or_proxy_kafka(operation: str):
    """Try native admin first; fall back to cluster-mgmt proxy."""
    try:
        return ("native", get_kafka_admin())
    except KafkaAdminUnavailableError as exc:
        logger.debug("kafka native unavailable for %s: %s", operation, exc)
    except KafkaAdminError as exc:
        logger.debug("kafka native error for %s: %s", operation, exc)
    try:
        from aqp.services.cluster_mgmt_client import get_cluster_mgmt_client

        return ("proxy", get_cluster_mgmt_client())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"kafka admin unavailable (native+proxy failed): {exc}",
        ) from exc


@router.get("/topics", response_model=list[TopicView])
def list_topics(include_internal: bool = False) -> list[TopicView]:
    backend, client = _native_or_proxy_kafka("list_topics")
    try:
        if backend == "native":
            return [TopicView(**t.to_dict()) for t in client.list_topics(include_internal=include_internal)]
        rows = client.kafka_topics()
        return [TopicView(**r) for r in rows]
    except KafkaAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/topics", response_model=TopicView, status_code=201)
def create_topic(req: CreateTopicRequest) -> TopicView:
    backend, client = _native_or_proxy_kafka("create_topic")
    try:
        if backend == "native":
            row = client.create_topic(
                req.name,
                partitions=req.partitions,
                replication_factor=req.replication_factor,
                config=req.config,
            )
            return TopicView(**row.to_dict())
        row = client.kafka_create_topic(
            name=req.name,
            partitions=req.partitions,
            replication_factor=req.replication_factor,
            config=req.config,
        )
        return TopicView(**row)
    except KafkaAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/topics/{name}", response_model=TopicView)
def get_topic(name: str) -> TopicView:
    backend, client = _native_or_proxy_kafka("get_topic")
    try:
        if backend == "native":
            return TopicView(**client.get_topic(name).to_dict())
        return TopicView(**client.kafka_topic(name))
    except KafkaAdminError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/topics/{name}", status_code=204, response_class=Response)
def delete_topic(name: str) -> Response:
    backend, client = _native_or_proxy_kafka("delete_topic")
    try:
        if backend == "native":
            client.delete_topic(name)
        else:
            client.kafka_delete_topic(name)
    except KafkaAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/topics/{name}/messages", response_model=list[TopicSampleMessage])
async def sample_topic_messages(name: str, limit: int = 100, timeout_s: float = 5.0) -> list[TopicSampleMessage]:
    try:
        admin = get_kafka_admin()
        rows = await admin.sample_messages(name, limit=limit, timeout_s=timeout_s)
        return [TopicSampleMessage(**r) for r in rows]
    except KafkaAdminUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KafkaAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/topics/{name}/produce")
async def produce_topic_message(name: str, req: ProduceRequest) -> dict[str, Any]:
    """Produce a JSON test message to a topic via the cluster bridge or native producer."""
    try:
        from aqp.services.cluster_mgmt_client import get_cluster_mgmt_client

        client = get_cluster_mgmt_client()
        return client.kafka_produce(
            topic=name,
            records=[{"key": req.key, "value": req.value}],
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"produce failed: {exc}") from exc


@router.get("/consumer-groups", response_model=list[ConsumerGroupView])
def list_consumer_groups() -> list[ConsumerGroupView]:
    backend, client = _native_or_proxy_kafka("list_consumer_groups")
    try:
        if backend == "native":
            return [ConsumerGroupView(**g.to_dict()) for g in client.list_consumer_groups()]
        return [ConsumerGroupView(**g) for g in client.kafka_consumer_groups()]
    except KafkaAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/consumer-groups/{group}/lag", response_model=ConsumerLagView)
def consumer_group_lag(group: str) -> ConsumerLagView:
    try:
        admin = get_kafka_admin()
        data = admin.get_consumer_group_lag(group)
        return ConsumerLagView(
            group_id=group,
            partitions=[ConsumerLagPartition(**p) for p in data.get("partitions", [])],
        )
    except KafkaAdminUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KafkaAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/schema-registry/subjects", response_model=list[SchemaSubjectView])
def list_subjects() -> list[SchemaSubjectView]:
    try:
        registry = get_schema_registry()
        return [SchemaSubjectView(subject=s) for s in registry.list_subjects()]
    except SchemaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/schema-registry/subjects/{subject}/versions/latest",
    response_model=SchemaVersionView,
)
def latest_subject_version(subject: str) -> SchemaVersionView:
    try:
        registry = get_schema_registry()
        data = registry.latest_version(subject)
        return SchemaVersionView(
            subject=subject,
            id=int(data.get("id")) if data.get("id") is not None else None,
            version=int(data.get("version")) if data.get("version") is not None else None,
            schema=data.get("schema"),
            schema_type=data.get("schemaType", "AVRO"),
        )
    except SchemaRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/schema-registry/subjects/{subject}/versions", response_model=SchemaVersionView)
def register_subject_version(subject: str, req: RegisterSchemaRequest) -> SchemaVersionView:
    try:
        registry = get_schema_registry()
        data = registry.register_schema(
            subject,
            schema=req.schema,
            schema_type=req.schema_type,
            references=req.references,
        )
        return SchemaVersionView(
            subject=subject,
            id=int(data.get("id")) if data.get("id") is not None else None,
            version=int(data.get("version")) if data.get("version") is not None else None,
            schema=data.get("schema"),
            schema_type=data.get("schemaType", req.schema_type),
        )
    except SchemaRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]
