"""``/cluster`` REST surface — pluggable :class:`KubernetesAdapter`.

These endpoints re-expose cluster-level operations under AQP's auth /
tenancy layer so users do not have to talk to two backends. Native
Kafka and Flink admin lives at ``/streaming/{kafka,flink}/*`` — this
proxy is the source of truth for cluster-only resources (Strimzi
users, Kafka Connect connectors, generic Deployment scaling, Alpha
Vantage producer toggle).

The legacy mount path ``/cluster-mgmt/*`` continues to work via the
:data:`legacy_router` alias so existing clients are unaffected.

The behaviour is identical regardless of which
:class:`aqp.kubernetes.KubernetesAdapter` is active — :class:`NoneAdapter`
returns 503, :class:`RpiClusterAdapter` forwards to the rpi management
HTTP API, :class:`InClusterAdapter` calls the K8s SDK directly, and
:class:`LocalComposeAdapter` wraps ``docker compose``.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from aqp.kubernetes import (
    KubernetesAdapter,
    KubernetesAdapterError,
    KubernetesAdapterUnavailable,
    get_kubernetes_adapter,
)

logger = logging.getLogger(__name__)


_routes = APIRouter(tags=["streaming", "cluster"])
router = APIRouter(prefix="/cluster", tags=["streaming", "cluster"])
legacy_router = APIRouter(prefix="/cluster-mgmt", tags=["streaming", "cluster"])


def _adapter() -> KubernetesAdapter:
    return get_kubernetes_adapter()


def _wrap_unavailable(exc: KubernetesAdapterUnavailable) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _wrap_error(exc: KubernetesAdapterError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Status / introspection
# ---------------------------------------------------------------------------


@_routes.get("/status")
def status() -> dict[str, Any]:
    return _adapter().describe()


# ---------------------------------------------------------------------------
# Kafka
# ---------------------------------------------------------------------------


@_routes.get("/kafka/topics")
def kafka_topics() -> list[dict[str, Any]]:
    try:
        return _adapter().kafka_topics()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/kafka/users")
def kafka_users() -> list[dict[str, Any]]:
    try:
        return _adapter().kafka_users()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


class KafkaUserCreate(BaseModel):
    name: str
    authentication: dict[str, Any] = Field(default_factory=dict)
    authorization: dict[str, Any] | None = None


@_routes.post("/kafka/users")
def create_kafka_user(body: KafkaUserCreate) -> dict[str, Any]:
    try:
        return _adapter().kafka_create_user(body.model_dump(mode="json"))
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.delete("/kafka/users/{name}", status_code=204, response_class=Response)
def delete_kafka_user(name: str) -> Response:
    try:
        _adapter().kafka_delete_user(name)
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc
    return Response(status_code=204)


@_routes.get("/kafka/users/{name}/secret")
def kafka_user_secret(name: str) -> dict[str, Any]:
    try:
        return _adapter().kafka_user_secret(name)
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/kafka/connectors")
def kafka_connectors() -> list[dict[str, Any]]:
    try:
        return _adapter().kafka_connectors()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.patch("/kafka/connectors/{name}/state")
def kafka_patch_connector(name: str, state: str) -> dict[str, Any]:
    try:
        return _adapter().kafka_patch_connector(name, state)
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/kafka/consumer-groups")
def kafka_consumer_groups() -> list[dict[str, Any]]:
    try:
        return _adapter().kafka_consumer_groups()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/kafka/schema-registry/subjects")
def kafka_schema_subjects() -> list[dict[str, Any]]:
    try:
        return _adapter().kafka_schema_subjects()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


# ---------------------------------------------------------------------------
# Flink
# ---------------------------------------------------------------------------


@_routes.get("/flink/deployments")
def flink_deployments() -> list[dict[str, Any]]:
    try:
        return _adapter().flink_deployments()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/flink/sessionjobs")
def flink_session_jobs(namespace: str | None = None) -> list[dict[str, Any]]:
    try:
        return _adapter().flink_session_jobs(namespace=namespace)
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/flink/jobs")
def flink_jobs() -> list[dict[str, Any]]:
    try:
        return _adapter().flink_jobs()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/flink/jobs/{job_id}")
def flink_job(job_id: str) -> dict[str, Any]:
    try:
        return _adapter().flink_job(job_id)
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


# ---------------------------------------------------------------------------
# Alpha Vantage
# ---------------------------------------------------------------------------


class AlphaVantageStreamRequest(BaseModel):
    enable: bool
    replicas: int = 1


@_routes.post("/alphavantage/stream")
def alphavantage_stream(req: AlphaVantageStreamRequest) -> dict[str, Any]:
    try:
        return _adapter().alphavantage_stream(enable=req.enable, replicas=req.replicas)
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/alphavantage/health")
def alphavantage_health() -> dict[str, Any]:
    try:
        return _adapter().alphavantage_health()
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


# ---------------------------------------------------------------------------
# Mount the shared route table on both prefixes (forwards-compatible).
# ---------------------------------------------------------------------------

router.include_router(_routes)
legacy_router.include_router(_routes)


__all__ = ["router", "legacy_router"]
