"""Hardware monitoring API endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..models.hardware import ClusterHardwareOverview, HardwareMetrics, NodeHardwareInfo
from ..services import HardwareService, KubernetesService, RedisService
from .redis_admin import get_redis_service

router = APIRouter()


def get_hardware_service(
    settings: Settings = Depends(get_settings),
) -> HardwareService:
    """Get hardware service instance."""
    return HardwareService(settings)


def get_k8s_service(settings: Settings = Depends(get_settings)) -> KubernetesService:
    """Get Kubernetes service instance."""
    return KubernetesService(settings)


@router.get("", response_model=ClusterHardwareOverview)
async def get_cluster_hardware(
    hardware: HardwareService = Depends(get_hardware_service),
    k8s: KubernetesService = Depends(get_k8s_service),
    redis: RedisService = Depends(get_redis_service),
) -> ClusterHardwareOverview:
    """Get hardware overview for all cluster nodes (cached 30s via Redis).

    The underlying `HardwareService` still performs per-node SSH probes on
    a cache miss; the Redis-backed cache-aside replaces the previous
    in-process ``_node_cache`` so horizontally scaled management pods
    share results.
    """
    try:
        data = await redis.cached_call(
            namespace="hardware",
            identifier="overview",
            fetch=lambda: _fetch_cluster_hardware(hardware, k8s),
            ttl=30,
        )
        if isinstance(data, ClusterHardwareOverview):
            return data
        return ClusterHardwareOverview(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_cluster_hardware(
    hardware: HardwareService, k8s: KubernetesService
) -> dict:
    nodes = await k8s.list_nodes()
    node_ips = {node.name: node.ip_address for node in nodes}
    overview = await hardware.get_cluster_hardware_overview(node_ips)
    return (
        overview.model_dump() if hasattr(overview, "model_dump") else overview.dict()
    )


@router.get("/{node_name}", response_model=NodeHardwareInfo)
async def get_node_hardware(
    node_name: str,
    hardware: HardwareService = Depends(get_hardware_service),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> NodeHardwareInfo:
    """Get hardware information for a specific node."""
    try:
        # Get node IP from Kubernetes
        node = await k8s.get_node(node_name)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_name} not found")

        return await hardware.get_node_hardware_info(node.ip_address, node_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{node_name}/metrics", response_model=HardwareMetrics)
async def get_node_metrics(
    node_name: str,
    hardware: HardwareService = Depends(get_hardware_service),
    k8s: KubernetesService = Depends(get_k8s_service),
) -> HardwareMetrics:
    """Get current hardware metrics for a specific node."""
    try:
        # Get node IP from Kubernetes
        node = await k8s.get_node(node_name)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_name} not found")

        metrics = await hardware.get_node_metrics(node.ip_address)
        if not metrics:
            raise HTTPException(
                status_code=503,
                detail=f"Unable to collect metrics from {node_name}",
            )
        return metrics
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
