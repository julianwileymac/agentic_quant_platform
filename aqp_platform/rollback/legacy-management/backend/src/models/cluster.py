"""Cluster-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    """Node status enumeration."""

    READY = "Ready"
    NOT_READY = "NotReady"
    UNKNOWN = "Unknown"


class PodPhase(str, Enum):
    """Pod phase enumeration."""

    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    UNKNOWN = "Unknown"


class NodeMetrics(BaseModel):
    """Resource metrics for a node."""

    cpu_capacity: str = Field(description="Total CPU capacity")
    cpu_allocatable: str = Field(description="Allocatable CPU")
    cpu_usage: Optional[str] = Field(default=None, description="Current CPU usage")
    cpu_usage_percent: Optional[float] = Field(default=None, description="CPU usage percentage")

    memory_capacity: str = Field(description="Total memory capacity")
    memory_allocatable: str = Field(description="Allocatable memory")
    memory_usage: Optional[str] = Field(default=None, description="Current memory usage")
    memory_usage_percent: Optional[float] = Field(default=None, description="Memory usage %")

    pods_capacity: int = Field(description="Maximum pods")
    pods_running: int = Field(default=0, description="Currently running pods")


class NodeInfo(BaseModel):
    """Information about a cluster node."""

    name: str = Field(description="Node name")
    status: NodeStatus = Field(description="Node status")
    roles: list[str] = Field(default_factory=list, description="Node roles")
    ip_address: str = Field(description="Node IP address")
    architecture: str = Field(description="CPU architecture (amd64/arm64)")
    os_image: str = Field(description="Operating system image")
    kernel_version: str = Field(description="Kernel version")
    container_runtime: str = Field(description="Container runtime version")
    kubelet_version: str = Field(description="Kubelet version")
    created_at: datetime = Field(description="Node creation timestamp")
    labels: dict[str, str] = Field(default_factory=dict, description="Node labels")
    taints: list[str] = Field(default_factory=list, description="Node taints")
    conditions: dict[str, str] = Field(default_factory=dict, description="Node conditions")
    metrics: Optional[NodeMetrics] = Field(default=None, description="Resource metrics")


class PodInfo(BaseModel):
    """Information about a pod."""

    name: str = Field(description="Pod name")
    namespace: str = Field(description="Pod namespace")
    phase: PodPhase = Field(description="Pod phase")
    node_name: Optional[str] = Field(default=None, description="Node running the pod")
    ip_address: Optional[str] = Field(default=None, description="Pod IP address")
    containers: list[str] = Field(default_factory=list, description="Container names")
    restarts: int = Field(default=0, description="Total container restarts")
    created_at: datetime = Field(description="Pod creation timestamp")
    labels: dict[str, str] = Field(default_factory=dict, description="Pod labels")


class ServiceInfo(BaseModel):
    """Information about a Kubernetes service."""

    name: str = Field(description="Service name")
    namespace: str = Field(description="Service namespace")
    type: str = Field(description="Service type (ClusterIP, LoadBalancer, etc.)")
    cluster_ip: Optional[str] = Field(default=None, description="Cluster IP")
    external_ip: Optional[str] = Field(default=None, description="External IP")
    ports: list[dict] = Field(default_factory=list, description="Service ports")
    selector: dict[str, str] = Field(default_factory=dict, description="Pod selector")
    created_at: datetime = Field(description="Service creation timestamp")


class ClusterInfo(BaseModel):
    """Overall cluster information."""

    name: str = Field(description="Cluster name")
    version: str = Field(description="Kubernetes version")
    node_count: int = Field(description="Total number of nodes")
    ready_nodes: int = Field(description="Number of ready nodes")
    total_pods: int = Field(description="Total pods in cluster")
    running_pods: int = Field(description="Running pods")
    total_cpu: str = Field(description="Total CPU capacity")
    total_memory: str = Field(description="Total memory capacity")
    namespaces: list[str] = Field(default_factory=list, description="Cluster namespaces")
    nodes: list[NodeInfo] = Field(default_factory=list, description="Node details")
