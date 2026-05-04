"""``/cluster-mgmt`` REST surface — proxy to the rpi_kubernetes management API.

These endpoints re-expose cluster-level operations under AQP's auth /
tenancy layer so users do not have to talk to two backends. Native
Kafka and Flink admin lives at ``/streaming/{kafka,flink}/*`` — this
proxy is the source of truth for cluster-only resources (Strimzi
users, Kafka Connect connectors, generic Deployment scaling, Alpha
Vantage producer toggle).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from aqp.services.cluster_mgmt_client import (
    ClusterMgmtClient,
    ClusterMgmtError,
    get_cluster_mgmt_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cluster-mgmt", tags=["streaming", "cluster"])


def _client() -> ClusterMgmtClient:
    client = get_cluster_mgmt_client()
    if not client.configured:
        raise HTTPException(
            status_code=503,
            detail="cluster_mgmt_url not configured (set AQP_CLUSTER_MGMT_URL)",
        )
    return client


# --- kafka ----------------------------------------------------------------
@router.get("/kafka/topics")
def kafka_topics() -> list[dict[str, Any]]:
    try:
        return _client().kafka_topics()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/kafka/users")
def kafka_users() -> list[dict[str, Any]]:
    try:
        return _client().kafka_users()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class KafkaUserCreate(BaseModel):
    name: str
    authentication: dict[str, Any] = Field(default_factory=dict)
    authorization: dict[str, Any] | None = None


@router.post("/kafka/users")
def create_kafka_user(body: KafkaUserCreate) -> dict[str, Any]:
    try:
        return _client().kafka_create_user(body.model_dump(mode="json"))
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/kafka/users/{name}", status_code=204, response_class=Response)
def delete_kafka_user(name: str) -> Response:
    try:
        _client().kafka_delete_user(name)
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/kafka/users/{name}/secret")
def kafka_user_secret(name: str) -> dict[str, Any]:
    try:
        return _client().kafka_user_secret(name)
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/kafka/connectors")
def kafka_connectors() -> list[dict[str, Any]]:
    try:
        return _client().kafka_connectors()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.patch("/kafka/connectors/{name}/state")
def kafka_patch_connector(name: str, state: str) -> dict[str, Any]:
    try:
        return _client().kafka_patch_connector(name, state)
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/kafka/consumer-groups")
def kafka_consumer_groups() -> list[dict[str, Any]]:
    try:
        return _client().kafka_consumer_groups()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/kafka/schema-registry/subjects")
def kafka_schema_subjects() -> list[dict[str, Any]]:
    try:
        return _client().kafka_schema_subjects()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# --- flink ----------------------------------------------------------------
@router.get("/flink/deployments")
def flink_deployments() -> list[dict[str, Any]]:
    try:
        return _client().flink_deployments()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/flink/sessionjobs")
def flink_session_jobs(namespace: str | None = None) -> list[dict[str, Any]]:
    try:
        return _client().flink_session_jobs(namespace=namespace)
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/flink/jobs")
def flink_jobs() -> list[dict[str, Any]]:
    try:
        return _client().flink_jobs()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/flink/jobs/{job_id}")
def flink_job(job_id: str) -> dict[str, Any]:
    try:
        return _client().flink_job(job_id)
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# --- alpha vantage producer toggle ---------------------------------------
class AlphaVantageStreamRequest(BaseModel):
    enable: bool
    replicas: int = 1


@router.post("/alphavantage/stream")
def alphavantage_stream(req: AlphaVantageStreamRequest) -> dict[str, Any]:
    try:
        return _client().alphavantage_stream(enable=req.enable, replicas=req.replicas)
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/alphavantage/health")
def alphavantage_health() -> dict[str, Any]:
    try:
        return _client().alphavantage_health()
    except ClusterMgmtError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]
