"""Cluster management API endpoints."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..config import Settings, get_settings
from ..models.cluster import ClusterInfo, NodeInfo, PodInfo, ServiceInfo
from ..services import KubernetesService, RedisService
from .redis_admin import get_redis_service

router = APIRouter()
logger = logging.getLogger(__name__)


def get_k8s_service(settings: Settings = Depends(get_settings)) -> KubernetesService:
    """Get Kubernetes service instance."""
    return KubernetesService(settings)


@router.get("", response_model=ClusterInfo)
async def get_cluster_info(
    k8s: KubernetesService = Depends(get_k8s_service),
    redis: RedisService = Depends(get_redis_service),
) -> ClusterInfo:
    """Get overall cluster information (cached 30s via Redis)."""
    try:
        data = await redis.cached_call(
            namespace="cluster",
            identifier="info",
            fetch=lambda: _fetch_cluster_info(k8s),
            ttl=30,
        )
        if isinstance(data, ClusterInfo):
            return data
        return ClusterInfo(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_cluster_info(k8s: KubernetesService) -> dict:
    info = await k8s.get_cluster_info()
    return info.model_dump() if hasattr(info, "model_dump") else info.dict()


@router.get("/nodes", response_model=list[NodeInfo])
async def list_nodes(
    k8s: KubernetesService = Depends(get_k8s_service),
    redis: RedisService = Depends(get_redis_service),
) -> list[NodeInfo]:
    """List all cluster nodes (cached 30s via Redis)."""
    try:
        rows = await redis.cached_call(
            namespace="cluster",
            identifier="nodes",
            fetch=lambda: _fetch_nodes(k8s),
            ttl=30,
        )
        return [NodeInfo(**row) if isinstance(row, dict) else row for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_nodes(k8s: KubernetesService) -> list[dict]:
    nodes = await k8s.list_nodes()
    return [
        n.model_dump() if hasattr(n, "model_dump") else n.dict()
        for n in nodes
    ]


@router.get("/nodes/{name}", response_model=NodeInfo)
async def get_node(
    name: str,
    k8s: KubernetesService = Depends(get_k8s_service),
) -> NodeInfo:
    """Get a specific node by name."""
    try:
        node = await k8s.get_node(name)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {name} not found")
        return node
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pods", response_model=list[PodInfo])
async def list_pods(
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    label_selector: Optional[str] = Query(None, description="Label selector"),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[PodInfo]:
    """List pods in the cluster."""
    try:
        return await k8s.list_pods(namespace=namespace, label_selector=label_selector)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pods/{namespace}/{name}/logs")
async def get_pod_logs(
    namespace: str,
    name: str,
    container: Optional[str] = Query(None, description="Container name"),
    tail_lines: int = Query(100, ge=1, le=10000, description="Number of lines"),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> dict:
    """Get logs from a pod."""
    try:
        logs = await k8s.get_pod_logs(
            name=name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
        )
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=list[ServiceInfo])
async def list_services(
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[ServiceInfo]:
    """List services in the cluster."""
    try:
        return await k8s.list_services(namespace=namespace)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/namespaces", response_model=list[str])
async def list_namespaces(
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[str]:
    """List all namespaces."""
    try:
        return await k8s.get_namespaces()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Curated service catalog + roll-up summary used by the dashboard.
# ---------------------------------------------------------------------------


@router.get("/services/catalog", response_model=list[dict])
async def get_service_catalog(
    k8s: KubernetesService = Depends(get_k8s_service),
) -> list[dict]:
    """Return the static curated catalog of platform services."""

    return k8s.service_catalog()


@router.get("/services/summary", response_model=list[dict])
async def get_services_summary(
    k8s: KubernetesService = Depends(get_k8s_service),
    redis: RedisService = Depends(get_redis_service),
) -> list[dict]:
    """Return live status for every catalog entry in a single roll-up call."""

    async def _fetch() -> list[dict]:
        results: list[dict] = []
        catalog = k8s.service_catalog()
        for entry in catalog:
            try:
                results.append(await k8s.service_status(entry["key"]))
            except Exception as exc:  # noqa: BLE001
                logger.warning("service_status(%s) failed: %s", entry["key"], exc)
                results.append({**entry, "healthy": False, "error": str(exc)})
        return results

    try:
        return await redis.cached_call(
            namespace="cluster",
            identifier="services-summary",
            fetch=_fetch,
            ttl=15,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# WebSocket: tail pod logs in real time.
# Endpoint: /api/cluster/pods/{namespace}/{name}/logs/stream
# ---------------------------------------------------------------------------


@router.websocket("/pods/{namespace}/{name}/logs/stream")
async def stream_pod_logs(
    websocket: WebSocket,
    namespace: str,
    name: str,
    container: Optional[str] = Query(None),
    tail_lines: int = Query(200, ge=1, le=10000),
    settings: Settings = Depends(get_settings),
) -> None:
    """Stream pod logs to the browser over WebSocket."""

    await websocket.accept()
    k8s = KubernetesService(settings)
    try:
        async for line in k8s.tail_pod_logs(
            name=name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
        ):
            await websocket.send_text(line)
    except WebSocketDisconnect:
        logger.info("Client disconnected from log stream %s/%s", namespace, name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Log stream %s/%s crashed", namespace, name)
        try:
            await websocket.send_text(f"<stream error: {exc}>")
        finally:
            await websocket.close(code=1011)
    else:
        await websocket.close()


# ---------------------------------------------------------------------------
# WebSocket: in-browser exec / terminal.
# Endpoint: /api/cluster/pods/{namespace}/{name}/exec
# ---------------------------------------------------------------------------


@router.websocket("/pods/{namespace}/{name}/exec")
async def exec_pod_terminal(
    websocket: WebSocket,
    namespace: str,
    name: str,
    container: Optional[str] = Query(None),
    command: str = Query("/bin/sh", description="Shell command to exec"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Bidirectional terminal session for a pod via WebSocket.

    Audit: every session is logged with namespace/pod/container/command.
    """

    await websocket.accept()
    logger.warning(
        "EXEC session opened ns=%s pod=%s container=%s command=%s",
        namespace,
        name,
        container,
        command,
    )

    k8s = KubernetesService(settings)
    try:
        ws = k8s.exec_in_pod(
            name=name,
            namespace=namespace,
            container=container,
            command=[command],
            stdin=True,
            tty=True,
        )
    except Exception as exc:  # noqa: BLE001
        await websocket.send_text(f"<exec failed: {exc}>")
        await websocket.close(code=1011)
        return

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    async def _pump_stdout() -> None:
        while not stop_event.is_set() and ws.is_open():
            chunk = await loop.run_in_executor(None, ws.read_stdout, 0.5)
            if chunk:
                try:
                    await websocket.send_text(chunk)
                except Exception:
                    stop_event.set()
                    break
        stop_event.set()

    async def _pump_stderr() -> None:
        while not stop_event.is_set() and ws.is_open():
            chunk = await loop.run_in_executor(None, ws.read_stderr, 0.5)
            if chunk:
                try:
                    await websocket.send_text(chunk)
                except Exception:
                    stop_event.set()
                    break
        stop_event.set()

    async def _pump_stdin() -> None:
        while not stop_event.is_set():
            try:
                msg = await websocket.receive_text()
            except WebSocketDisconnect:
                stop_event.set()
                break
            if msg:
                try:
                    ws.write_stdin(msg)
                except Exception:
                    stop_event.set()
                    break

    pumps = [
        asyncio.create_task(_pump_stdout()),
        asyncio.create_task(_pump_stderr()),
        asyncio.create_task(_pump_stdin()),
    ]

    try:
        await stop_event.wait()
    finally:
        for task in pumps:
            task.cancel()
        try:
            ws.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(
            "EXEC session closed ns=%s pod=%s container=%s",
            namespace,
            name,
            container,
        )
