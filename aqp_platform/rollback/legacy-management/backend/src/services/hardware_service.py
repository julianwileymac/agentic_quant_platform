"""
Hardware monitoring service.

Collects hardware metrics from cluster nodes via SSH.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import asyncssh

from ..config import Settings
from ..models.hardware import (
    ClusterHardwareOverview,
    HardwareMetrics,
    NodeHardwareInfo,
    ThrottleStatus,
)

logger = logging.getLogger(__name__)


class HardwareService:
    """Service for hardware monitoring operations."""

    def __init__(self, settings: Settings):
        """Initialize the hardware service."""
        self.settings = settings
        self._node_cache: dict[str, NodeHardwareInfo] = {}

    async def _ssh_connect(self, host: str) -> asyncssh.SSHClientConnection:
        """Create SSH connection to a node."""
        connect_kwargs = {
            "host": host,
            "username": self.settings.hardware.ssh_user,
            "known_hosts": None,  # Disable host key checking for lab environment
            "connect_timeout": self.settings.hardware.ssh_timeout,
        }

        if self.settings.hardware.ssh_key_path:
            connect_kwargs["client_keys"] = [self.settings.hardware.ssh_key_path]

        return await asyncssh.connect(**connect_kwargs)

    async def _run_command(
        self,
        conn: asyncssh.SSHClientConnection,
        command: str,
    ) -> str:
        """Run a command over SSH and return output."""
        result = await conn.run(command, check=False)
        return result.stdout.strip() if result.stdout else ""

    async def get_node_metrics(self, host: str) -> Optional[HardwareMetrics]:
        """Collect hardware metrics from a node via SSH."""
        try:
            async with await self._ssh_connect(host) as conn:
                # Collect all metrics in parallel
                results = await asyncio.gather(
                    self._run_command(conn, "cat /proc/loadavg"),
                    self._run_command(conn, "free -m"),
                    self._run_command(conn, "df -BG /"),
                    self._run_command(conn, "cat /proc/stat | head -1"),
                    self._run_command(conn, "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo ''"),
                    self._run_command(conn, "vcgencmd measure_temp 2>/dev/null || echo ''"),
                    self._run_command(conn, "vcgencmd get_throttled 2>/dev/null || echo ''"),
                    self._run_command(conn, "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || echo ''"),
                    self._run_command(conn, "cat /proc/net/dev | grep -E 'eth0|wlan0' | head -1"),
                    return_exceptions=True,
                )

                # Parse load average
                loadavg_parts = results[0].split() if isinstance(results[0], str) else []
                load_1m = float(loadavg_parts[0]) if len(loadavg_parts) > 0 else 0.0
                load_5m = float(loadavg_parts[1]) if len(loadavg_parts) > 1 else 0.0
                load_15m = float(loadavg_parts[2]) if len(loadavg_parts) > 2 else 0.0

                # Parse memory
                mem_lines = results[1].split("\n") if isinstance(results[1], str) else []
                mem_total = mem_used = mem_available = 0.0
                for line in mem_lines:
                    if line.startswith("Mem:"):
                        parts = line.split()
                        mem_total = float(parts[1])
                        mem_used = float(parts[2])
                        mem_available = float(parts[6]) if len(parts) > 6 else mem_total - mem_used

                # Parse disk
                disk_lines = results[2].split("\n") if isinstance(results[2], str) else []
                disk_total = disk_used = disk_available = 0.0
                for line in disk_lines:
                    if "/" in line and not line.startswith("Filesystem"):
                        parts = line.split()
                        if len(parts) >= 4:
                            disk_total = float(parts[1].rstrip("G"))
                            disk_used = float(parts[2].rstrip("G"))
                            disk_available = float(parts[3].rstrip("G"))

                # Parse CPU usage (simplified - would need two samples for accurate %)
                cpu_usage = load_1m * 25  # Rough approximation based on load

                # Parse temperature
                cpu_temp = None
                if isinstance(results[4], str) and results[4]:
                    try:
                        cpu_temp = float(results[4]) / 1000.0
                    except ValueError:
                        pass

                # Parse RPi temperature from vcgencmd
                gpu_temp = None
                if isinstance(results[5], str) and "temp=" in results[5]:
                    match = re.search(r"temp=([\d.]+)", results[5])
                    if match:
                        gpu_temp = float(match.group(1))
                        if cpu_temp is None:
                            cpu_temp = gpu_temp

                # Parse throttle status
                throttle_status = []
                if isinstance(results[6], str) and "throttled=" in results[6]:
                    match = re.search(r"throttled=(0x[0-9a-fA-F]+)", results[6])
                    if match:
                        throttle_val = int(match.group(1), 16)
                        if throttle_val & 0x1:
                            throttle_status.append(ThrottleStatus.UNDER_VOLTAGE)
                        if throttle_val & 0x2:
                            throttle_status.append(ThrottleStatus.ARM_FREQUENCY_CAPPED)
                        if throttle_val & 0x4:
                            throttle_status.append(ThrottleStatus.THROTTLED)
                        if throttle_val & 0x8:
                            throttle_status.append(ThrottleStatus.SOFT_TEMP_LIMIT)

                # Parse CPU frequency
                cpu_freq = None
                if isinstance(results[7], str) and results[7]:
                    try:
                        cpu_freq = float(results[7]) / 1000.0  # Convert kHz to MHz
                    except ValueError:
                        pass

                # Parse network stats
                rx_bytes = tx_bytes = 0
                if isinstance(results[8], str) and results[8]:
                    parts = results[8].split()
                    if len(parts) >= 10:
                        rx_bytes = int(parts[1])
                        tx_bytes = int(parts[9])

                return HardwareMetrics(
                    timestamp=datetime.now(timezone.utc),
                    cpu_temperature=cpu_temp,
                    cpu_frequency=cpu_freq,
                    cpu_usage_percent=min(cpu_usage, 100.0),
                    load_average_1m=load_1m,
                    load_average_5m=load_5m,
                    load_average_15m=load_15m,
                    memory_total_mb=mem_total,
                    memory_used_mb=mem_used,
                    memory_available_mb=mem_available,
                    memory_usage_percent=(mem_used / mem_total * 100) if mem_total > 0 else 0,
                    disk_total_gb=disk_total,
                    disk_used_gb=disk_used,
                    disk_available_gb=disk_available,
                    disk_usage_percent=(disk_used / disk_total * 100) if disk_total > 0 else 0,
                    network_rx_bytes=rx_bytes,
                    network_tx_bytes=tx_bytes,
                    throttle_status=throttle_status,
                    gpu_temperature=gpu_temp,
                )

        except Exception as e:
            logger.error(f"Failed to get metrics from {host}: {e}")
            return None

    async def get_node_hardware_info(self, host: str, node_name: str) -> NodeHardwareInfo:
        """Get complete hardware information for a node."""
        metrics = await self.get_node_metrics(host)
        online = metrics is not None

        # Try to get system info
        hardware_type = "unknown"
        model = None
        cpu_model = None
        cpu_cores = 0
        architecture = "unknown"
        uptime_seconds = 0

        if online:
            try:
                async with await self._ssh_connect(host) as conn:
                    results = await asyncio.gather(
                        self._run_command(conn, "cat /proc/cpuinfo | grep -E 'Model|model name|processor' | head -5"),
                        self._run_command(conn, "uname -m"),
                        self._run_command(conn, "cat /proc/uptime"),
                        self._run_command(conn, "nproc"),
                        return_exceptions=True,
                    )

                    # Parse CPU info
                    if isinstance(results[0], str):
                        if "Raspberry Pi" in results[0]:
                            hardware_type = "raspberry-pi"
                            match = re.search(r"Model\s*:\s*(.+)", results[0])
                            if match:
                                model = match.group(1).strip()
                        else:
                            hardware_type = "desktop"
                            match = re.search(r"model name\s*:\s*(.+)", results[0])
                            if match:
                                cpu_model = match.group(1).strip()

                    # Parse architecture
                    if isinstance(results[1], str):
                        architecture = results[1]

                    # Parse uptime
                    if isinstance(results[2], str):
                        uptime_parts = results[2].split()
                        if uptime_parts:
                            uptime_seconds = int(float(uptime_parts[0]))

                    # Parse CPU cores
                    if isinstance(results[3], str):
                        cpu_cores = int(results[3])

            except Exception as e:
                logger.error(f"Failed to get system info from {host}: {e}")

        return NodeHardwareInfo(
            node_name=node_name,
            ip_address=host,
            hardware_type=hardware_type,
            model=model,
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            architecture=architecture,
            uptime_seconds=uptime_seconds,
            last_boot=datetime.now(timezone.utc),  # Would calculate from uptime
            metrics=metrics,
            online=online,
            last_seen=datetime.now(timezone.utc),
        )

    async def get_cluster_hardware_overview(
        self,
        node_ips: dict[str, str],
    ) -> ClusterHardwareOverview:
        """Get hardware overview for all nodes in the cluster."""
        # Collect info from all nodes in parallel
        tasks = [
            self.get_node_hardware_info(ip, name)
            for name, ip in node_ips.items()
        ]
        nodes = await asyncio.gather(*tasks)

        # Calculate aggregates
        online_nodes = sum(1 for n in nodes if n.online)
        total_cpu_cores = sum(n.cpu_cores for n in nodes)
        total_memory_gb = sum(
            n.metrics.memory_total_mb / 1024 for n in nodes if n.metrics
        )
        total_storage_gb = sum(
            n.metrics.disk_total_gb for n in nodes if n.metrics
        )

        # Calculate averages
        cpu_usages = [n.metrics.cpu_usage_percent for n in nodes if n.metrics]
        mem_usages = [n.metrics.memory_usage_percent for n in nodes if n.metrics]
        temperatures = [
            n.metrics.cpu_temperature
            for n in nodes
            if n.metrics and n.metrics.cpu_temperature
        ]

        return ClusterHardwareOverview(
            total_nodes=len(nodes),
            online_nodes=online_nodes,
            total_cpu_cores=total_cpu_cores,
            total_memory_gb=total_memory_gb,
            total_storage_gb=total_storage_gb,
            average_cpu_usage=sum(cpu_usages) / len(cpu_usages) if cpu_usages else 0,
            average_memory_usage=sum(mem_usages) / len(mem_usages) if mem_usages else 0,
            average_temperature=sum(temperatures) / len(temperatures) if temperatures else None,
            nodes=list(nodes),
        )
