"""``/cluster`` REST surface — pluggable :class:`KubernetesAdapter`.

These endpoints re-expose cluster-level operations under AQP's auth /
tenancy layer so users do not have to talk to two backends. Native
Kafka and Flink admin lives at ``/streaming/{kafka,flink}/*`` — this
proxy is the source of truth for cluster-only resources (Strimzi
users, Kafka Connect connectors, generic Deployment scaling, Alpha
Vantage producer toggle, and Phase 1 pod-level ops).

The legacy mount path ``/cluster-mgmt/*`` continues to work via the
:data:`legacy_router` alias so existing clients are unaffected.

The behaviour is identical regardless of which
:class:`aqp.kubernetes.KubernetesAdapter` is active — :class:`NoneAdapter`
returns 503, :class:`RpiClusterAdapter` forwards to the rpi management
HTTP API, :class:`InClusterAdapter` calls the K8s SDK directly, and
:class:`LocalComposeAdapter` wraps the Docker Python SDK (with
``Accept-Encoding: identity`` so multi-gigabyte tar extracts don't
saturate the daemon).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import asdict
from typing import Any

from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
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
# Phase 1 — pod-level ops (list / exec / logs / archive)
# ---------------------------------------------------------------------------


def _pod_to_json(pod: Any) -> dict[str, Any]:
    try:
        return asdict(pod)
    except Exception:  # noqa: BLE001
        return dict(pod) if hasattr(pod, "__iter__") else {}


@_routes.get("/pods/{namespace}")
def list_pods(
    namespace: str,
    label_selector: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    try:
        return [_pod_to_json(p) for p in _adapter().list_pods(
            namespace=namespace, label_selector=label_selector
        )]
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


class PodExecRequest(BaseModel):
    command: list[str] = Field(..., min_length=1)
    container: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    stdin_b64: str | None = Field(
        default=None,
        description=(
            "Optional base64-encoded stdin payload. Only the in_cluster "
            "adapter honours this today; local_compose and rpi_cluster "
            "return 502 if set."
        ),
    )


@_routes.post("/pods/{namespace}/{name}/exec")
def pod_exec(namespace: str, name: str, body: PodExecRequest) -> dict[str, Any]:
    try:
        from aqp.config import settings

        default_timeout = int(getattr(settings, "k8s_exec_default_timeout", 120) or 120)
    except Exception:  # noqa: BLE001
        default_timeout = 120
    stdin: bytes | None = None
    if body.stdin_b64:
        try:
            stdin = base64.b64decode(body.stdin_b64)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"invalid stdin_b64: {exc}")
    try:
        result = _adapter().exec_in_pod(
            namespace=namespace,
            name=name,
            command=list(body.command),
            container=body.container,
            timeout_seconds=int(body.timeout_seconds or default_timeout),
            stdin=stdin,
        )
        return asdict(result)
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


@_routes.get("/pods/{namespace}/{name}/archive")
def pod_get_archive(
    namespace: str,
    name: str,
    path: str = Query(...),
    container: str | None = Query(default=None),
) -> Response:
    try:
        payload = _adapter().get_pod_archive(
            namespace=namespace, name=name, path=path, container=container
        )
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc
    return Response(
        content=payload,
        media_type="application/x-tar",
        headers={"Content-Disposition": f'attachment; filename="{name}-{path.lstrip("/")}.tar"'},
    )


class PodArchivePutRequest(BaseModel):
    path: str = Field(..., min_length=1)
    data_b64: str = Field(..., min_length=1)
    container: str | None = None


@_routes.post("/pods/{namespace}/{name}/archive")
def pod_put_archive(
    namespace: str, name: str, body: PodArchivePutRequest
) -> dict[str, Any]:
    try:
        data = base64.b64decode(body.data_b64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"invalid data_b64: {exc}")
    try:
        return _adapter().put_pod_archive(
            namespace=namespace,
            name=name,
            path=body.path,
            data=data,
            container=body.container,
        )
    except KubernetesAdapterUnavailable as exc:
        raise _wrap_unavailable(exc) from exc
    except KubernetesAdapterError as exc:
        raise _wrap_error(exc) from exc


# ---------------------------------------------------------------------------
# Mount the shared route table on both prefixes (forwards-compatible).
# ---------------------------------------------------------------------------

router.include_router(_routes)
legacy_router.include_router(_routes)


# ---------------------------------------------------------------------------
# WebSocket: pod log streaming.
#
# Lives on the prefixed routers directly (not on ``_routes``) because
# the throttling pipeline is shared with ``frontend/src/lib/ws/`` and
# the legacy ``/cluster-mgmt`` alias also needs it. Frames are shaped
# ``{task_id, stage, message, timestamp, **extras}`` per AGENTS rule 4.
# ---------------------------------------------------------------------------


async def _pod_logs_ws(
    ws: WebSocket,
    *,
    namespace: str,
    name: str,
    container: str | None,
    since_seconds: int | None,
    tail_lines: int | None,
    follow: bool,
) -> None:
    await ws.accept()
    try:
        from aqp.config import settings

        max_seconds = int(getattr(settings, "k8s_pod_log_max_seconds", 600) or 600)
        hard_max_lines = int(getattr(settings, "k8s_pod_log_max_lines", 10000) or 10000)
    except Exception:  # noqa: BLE001
        max_seconds = 600
        hard_max_lines = 10000

    deadline = time.time() + max(1, max_seconds)
    task_id = f"pod-logs:{namespace}:{name}"
    adapter = _adapter()

    async def _push(frame: dict[str, Any]) -> None:
        try:
            await ws.send_text(json.dumps(frame))
        except Exception:  # noqa: BLE001
            raise

    await _push({
        "task_id": task_id,
        "stage": "open",
        "message": f"streaming {namespace}/{name}",
        "timestamp": time.time(),
        "namespace": namespace,
        "name": name,
        "container": container,
    })

    loop = asyncio.get_event_loop()
    sent = 0

    def _iterate() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            for event in adapter.stream_pod_logs(
                namespace=namespace,
                name=name,
                container=container,
                since_seconds=since_seconds,
                tail_lines=tail_lines,
                follow=follow,
                max_lines=hard_max_lines,
            ):
                out.append(asdict(event))
                if len(out) >= 100:
                    break
        except KubernetesAdapterUnavailable as exc:
            out.append({"_error": "unavailable", "_detail": str(exc)})
        except KubernetesAdapterError as exc:
            out.append({"_error": "error", "_detail": str(exc)})
        return out

    try:
        while True:
            if time.time() > deadline:
                await _push({
                    "task_id": task_id,
                    "stage": "deadline",
                    "message": "max stream duration reached",
                    "timestamp": time.time(),
                })
                break
            try:
                events = await loop.run_in_executor(None, _iterate)
            except Exception as exc:  # noqa: BLE001
                logger.exception("pod logs ws iteration failed")
                await _push({
                    "task_id": task_id,
                    "stage": "error",
                    "message": str(exc),
                    "timestamp": time.time(),
                })
                break
            if not events:
                await asyncio.sleep(0.5)
                continue
            for event in events:
                if event.get("_error"):
                    await _push({
                        "task_id": task_id,
                        "stage": event["_error"],
                        "message": event.get("_detail", ""),
                        "timestamp": time.time(),
                    })
                    break
                await _push({
                    "task_id": task_id,
                    "stage": "line",
                    "message": event.get("line", ""),
                    "timestamp": time.time(),
                    "namespace": event.get("namespace", namespace),
                    "name": event.get("name", name),
                    "container": event.get("container"),
                    "log_timestamp": event.get("timestamp", ""),
                    "source": event.get("source", "stdout"),
                })
                sent += 1
                if sent >= hard_max_lines:
                    break
            if sent >= hard_max_lines:
                await _push({
                    "task_id": task_id,
                    "stage": "max_lines",
                    "message": f"reached max_lines={hard_max_lines}",
                    "timestamp": time.time(),
                })
                break
            if not follow:
                break
    except WebSocketDisconnect:
        return
    finally:
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


@router.websocket("/pods/{namespace}/{name}/logs/stream")
async def pod_logs_stream(
    ws: WebSocket,
    namespace: str,
    name: str,
    container: str | None = Query(default=None),
    since_seconds: int | None = Query(default=None),
    tail_lines: int | None = Query(default=None),
    follow: bool = Query(default=True),
) -> None:
    await _pod_logs_ws(
        ws,
        namespace=namespace,
        name=name,
        container=container,
        since_seconds=since_seconds,
        tail_lines=tail_lines,
        follow=follow,
    )


@legacy_router.websocket("/pods/{namespace}/{name}/logs/stream")
async def pod_logs_stream_legacy(
    ws: WebSocket,
    namespace: str,
    name: str,
    container: str | None = Query(default=None),
    since_seconds: int | None = Query(default=None),
    tail_lines: int | None = Query(default=None),
    follow: bool = Query(default=True),
) -> None:
    await _pod_logs_ws(
        ws,
        namespace=namespace,
        name=name,
        container=container,
        since_seconds=since_seconds,
        tail_lines=tail_lines,
        follow=follow,
    )


__all__ = ["router", "legacy_router"]
