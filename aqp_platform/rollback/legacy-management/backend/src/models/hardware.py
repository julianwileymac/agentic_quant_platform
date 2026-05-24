"""Hardware monitoring Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ThrottleStatus(str, Enum):
    """Throttling status for Raspberry Pi."""

    NONE = "none"
    UNDER_VOLTAGE = "under_voltage"
    ARM_FREQUENCY_CAPPED = "arm_frequency_capped"
    THROTTLED = "throttled"
    SOFT_TEMP_LIMIT = "soft_temp_limit"


class HardwareMetrics(BaseModel):
    """Hardware metrics from a node."""

    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Collection time")

    # CPU metrics
    cpu_temperature: Optional[float] = Field(
        default=None,
        description="CPU temperature in Celsius",
    )
    cpu_frequency: Optional[float] = Field(
        default=None,
        description="Current CPU frequency in MHz",
    )
    cpu_usage_percent: float = Field(description="CPU usage percentage")
    load_average_1m: float = Field(description="1-minute load average")
    load_average_5m: float = Field(description="5-minute load average")
    load_average_15m: float = Field(description="15-minute load average")

    # Memory metrics
    memory_total_mb: float = Field(description="Total memory in MB")
    memory_used_mb: float = Field(description="Used memory in MB")
    memory_available_mb: float = Field(description="Available memory in MB")
    memory_usage_percent: float = Field(description="Memory usage percentage")

    # Disk metrics
    disk_total_gb: float = Field(description="Total disk space in GB")
    disk_used_gb: float = Field(description="Used disk space in GB")
    disk_available_gb: float = Field(description="Available disk space in GB")
    disk_usage_percent: float = Field(description="Disk usage percentage")

    # Network metrics
    network_rx_bytes: int = Field(default=0, description="Bytes received")
    network_tx_bytes: int = Field(default=0, description="Bytes transmitted")

    # Raspberry Pi specific
    throttle_status: list[ThrottleStatus] = Field(
        default_factory=list,
        description="Current throttling status",
    )
    gpu_temperature: Optional[float] = Field(
        default=None,
        description="GPU temperature in Celsius (RPi)",
    )
    voltage: Optional[float] = Field(
        default=None,
        description="Core voltage (RPi)",
    )


class NodeHardwareInfo(BaseModel):
    """Complete hardware information for a node."""

    node_name: str = Field(description="Node name")
    ip_address: str = Field(description="Node IP address")
    hardware_type: str = Field(description="Hardware type (raspberry-pi, desktop)")
    model: Optional[str] = Field(default=None, description="Hardware model")
    serial: Optional[str] = Field(default=None, description="Serial number")
    cpu_model: Optional[str] = Field(default=None, description="CPU model")
    cpu_cores: int = Field(description="Number of CPU cores")
    architecture: str = Field(description="CPU architecture")
    uptime_seconds: int = Field(description="System uptime in seconds")
    last_boot: datetime = Field(description="Last boot timestamp")
    metrics: Optional[HardwareMetrics] = Field(default=None, description="Current metrics")
    online: bool = Field(default=True, description="Whether node is reachable")
    last_seen: datetime = Field(default_factory=datetime.utcnow, description="Last seen time")


class ClusterHardwareOverview(BaseModel):
    """Hardware overview for the entire cluster."""

    total_nodes: int = Field(description="Total nodes in cluster")
    online_nodes: int = Field(description="Online nodes")
    total_cpu_cores: int = Field(description="Total CPU cores")
    total_memory_gb: float = Field(description="Total memory in GB")
    total_storage_gb: float = Field(description="Total storage in GB")
    average_cpu_usage: float = Field(description="Average CPU usage across nodes")
    average_memory_usage: float = Field(description="Average memory usage")
    average_temperature: Optional[float] = Field(
        default=None,
        description="Average CPU temperature",
    )
    nodes: list[NodeHardwareInfo] = Field(default_factory=list, description="Per-node details")
