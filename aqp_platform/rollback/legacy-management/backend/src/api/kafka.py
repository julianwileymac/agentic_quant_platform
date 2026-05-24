"""Kafka management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..models.kafka import (
    KafkaConnectorInfo,
    KafkaConsumerGroupInfo,
    KafkaProduceRequest,
    KafkaTopicCreate,
    KafkaTopicInfo,
    KafkaUserCreate,
    KafkaUserInfo,
    SchemaRegistrySubject,
)
from ..services import KafkaService, KubernetesService

router = APIRouter()


def get_kafka_service(settings: Settings = Depends(get_settings)) -> KafkaService:
    k8s = KubernetesService(settings)
    return KafkaService(settings, k8s)


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


@router.get("/topics", response_model=list[KafkaTopicInfo])
async def list_topics(service: KafkaService = Depends(get_kafka_service)):
    try:
        return await service.list_topics()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/topics/{name}", response_model=KafkaTopicInfo)
async def get_topic(name: str, service: KafkaService = Depends(get_kafka_service)):
    topic = await service.get_topic(name)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"topic {name} not found")
    return topic


@router.post("/topics", response_model=KafkaTopicInfo, status_code=201)
async def create_topic(
    payload: KafkaTopicCreate,
    service: KafkaService = Depends(get_kafka_service),
):
    try:
        return await service.create_topic(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/topics/{name}", status_code=204)
async def delete_topic(name: str, service: KafkaService = Depends(get_kafka_service)):
    try:
        await service.delete_topic(name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/topics/{name}/produce")
async def produce(
    name: str,
    payload: KafkaProduceRequest,
    service: KafkaService = Depends(get_kafka_service),
):
    try:
        return await service.produce_via_bridge(name, payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[KafkaUserInfo])
async def list_users(service: KafkaService = Depends(get_kafka_service)):
    return await service.list_users()


@router.post("/users", response_model=KafkaUserInfo, status_code=201)
async def create_user(
    payload: KafkaUserCreate,
    service: KafkaService = Depends(get_kafka_service),
):
    return await service.create_user(payload)


@router.delete("/users/{name}", status_code=204)
async def delete_user(name: str, service: KafkaService = Depends(get_kafka_service)):
    await service.delete_user(name)


@router.get("/users/{name}/secret")
async def get_user_secret(name: str, service: KafkaService = Depends(get_kafka_service)):
    secret = await service.get_user_secret(name)
    if secret is None:
        raise HTTPException(status_code=404, detail=f"secret {name} not found")
    return secret


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------


@router.get("/connectors", response_model=list[KafkaConnectorInfo])
async def list_connectors(service: KafkaService = Depends(get_kafka_service)):
    return await service.list_connectors()


@router.patch("/connectors/{name}/state")
async def patch_connector_state(
    name: str,
    state: str,
    service: KafkaService = Depends(get_kafka_service),
):
    """State must be one of `paused` or `running`."""
    if state not in ("paused", "running", "stopped"):
        raise HTTPException(status_code=400, detail="invalid state")
    return await service.patch_connector_state(name, state)


# ---------------------------------------------------------------------------
# Consumer groups
# ---------------------------------------------------------------------------


@router.get("/consumer-groups", response_model=list[KafkaConsumerGroupInfo])
async def list_consumer_groups(service: KafkaService = Depends(get_kafka_service)):
    return await service.list_consumer_groups()


# ---------------------------------------------------------------------------
# Schema registry proxy
# ---------------------------------------------------------------------------


@router.get("/schema-registry/subjects", response_model=list[SchemaRegistrySubject])
async def list_schema_subjects(service: KafkaService = Depends(get_kafka_service)):
    return await service.list_schema_subjects()
