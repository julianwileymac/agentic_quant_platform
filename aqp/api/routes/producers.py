"""``/streaming/producers`` REST surface.

Lifecycle controls for every Kafka-bound market-data producer
(Alpha-Vantage, IBKR, Alpaca, polygon, synthetic, custom). Backed by
:class:`aqp.streaming.producers.supervisor.ProducerSupervisor`, which
delegates to the cluster-mgmt proxy for kubernetes-deployed
producers and to a local subprocess for development workstations.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from aqp.persistence.db import get_session
from aqp.streaming.producers import (
    ProducerError,
    get_supervisor,
)
from aqp.streaming.producers.supervisor import _producer_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/streaming/producers", tags=["streaming"])


class ProducerView(BaseModel):
    id: str
    name: str
    kind: str
    runtime: str
    display_name: str
    description: str | None = None
    deployment_namespace: str | None = None
    deployment_name: str | None = None
    image: str | None = None
    topics: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    desired_replicas: int = 0
    current_replicas: int = 0
    last_status: str = "unknown"
    last_status_at: str | None = None
    last_error: str | None = None
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class ProducerCreateRequest(BaseModel):
    name: str
    kind: str = "custom"
    runtime: str = "kubernetes"
    display_name: str | None = None
    description: str | None = None
    deployment_namespace: str | None = None
    deployment_name: str | None = None
    image: str | None = None
    topics: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    env_overrides: dict[str, Any] = Field(default_factory=dict)
    desired_replicas: int = 0
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class ProducerPatchRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    deployment_namespace: str | None = None
    deployment_name: str | None = None
    image: str | None = None
    runtime: str | None = None
    kind: str | None = None
    topics: list[str] | None = None
    config: dict[str, Any] | None = None
    env_overrides: dict[str, Any] | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    desired_replicas: int | None = None


class ScaleRequest(BaseModel):
    replicas: int | None = None


class StatusView(BaseModel):
    name: str
    current_replicas: int
    desired_replicas: int
    ready: bool
    message: str
    last_status: str | None = None
    last_status_at: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LogsView(BaseModel):
    name: str
    pod: str | None = None
    lines: list[str] = Field(default_factory=list)


@router.get("", response_model=list[ProducerView])
def list_producers() -> list[ProducerView]:
    supervisor = get_supervisor()
    with get_session() as session:
        supervisor.seed_catalog(session)
        rows = supervisor.list(session)
        return [ProducerView(**_producer_summary(r)) for r in rows]


@router.post("", response_model=ProducerView, status_code=201)
def create_producer(req: ProducerCreateRequest) -> ProducerView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            row = supervisor.create(session, **req.model_dump(mode="json"))
        except ProducerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ProducerView(**_producer_summary(row))


@router.get("/{name}", response_model=ProducerView)
def get_producer(name: str) -> ProducerView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            row = supervisor.get(session, name)
        except ProducerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ProducerView(**_producer_summary(row))


@router.patch("/{name}", response_model=ProducerView)
def patch_producer(name: str, req: ProducerPatchRequest) -> ProducerView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            row = supervisor.patch(session, name, **req.model_dump(mode="json", exclude_unset=True))
        except ProducerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ProducerView(**_producer_summary(row))


@router.delete("/{name}", status_code=204, response_class=Response)
def delete_producer(name: str) -> Response:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            supervisor.delete(session, name)
        except ProducerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/{name}/start", response_model=StatusView)
def start_producer(name: str, req: ScaleRequest | None = None) -> StatusView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            data = supervisor.start(session, name, replicas=(req.replicas if req else None))
        except ProducerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return StatusView(**data)


@router.post("/{name}/stop", response_model=StatusView)
def stop_producer(name: str) -> StatusView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            data = supervisor.stop(session, name)
        except ProducerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return StatusView(**data)


@router.post("/{name}/scale", response_model=StatusView)
def scale_producer(name: str, req: ScaleRequest) -> StatusView:
    if req.replicas is None:
        raise HTTPException(status_code=400, detail="replicas is required")
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            data = supervisor.scale(session, name, replicas=int(req.replicas))
        except ProducerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return StatusView(**data)


@router.post("/{name}/restart", response_model=StatusView)
def restart_producer(name: str) -> StatusView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            data = supervisor.restart(session, name)
        except ProducerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return StatusView(**data)


@router.get("/{name}/status", response_model=StatusView)
def status_producer(name: str) -> StatusView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            data = supervisor.status(session, name)
        except ProducerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return StatusView(**data)


@router.get("/{name}/logs", response_model=LogsView)
def logs_producer(name: str, tail: int = 200) -> LogsView:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            data = supervisor.logs(session, name, tail=tail)
        except ProducerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return LogsView(**data)


@router.get("/{name}/topics")
def topics_for_producer(name: str) -> dict[str, Any]:
    supervisor = get_supervisor()
    with get_session() as session:
        try:
            row = supervisor.get(session, name)
        except ProducerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        topics = list(row.topics or [])
        # Cross-reference streaming_dataset_links if available
        links: list[dict[str, Any]] = []
        try:
            from aqp.persistence import StreamingDatasetLink

            for topic in topics:
                rows = (
                    session.query(StreamingDatasetLink)
                    .filter(
                        StreamingDatasetLink.kind == "kafka_topic",
                        StreamingDatasetLink.target_ref == topic,
                    )
                    .all()
                )
                for link in rows:
                    links.append(
                        {
                            "id": link.id,
                            "kind": link.kind,
                            "target_ref": link.target_ref,
                            "dataset_namespace": link.dataset_namespace,
                            "dataset_table": link.dataset_table,
                            "direction": link.direction,
                        }
                    )
        except Exception:  # noqa: BLE001
            pass
        return {"producer": name, "topics": topics, "links": links}


__all__ = ["router"]
