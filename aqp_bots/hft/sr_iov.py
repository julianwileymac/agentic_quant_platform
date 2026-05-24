"""SR-IOV NIC awareness.

Single Root I/O Virtualization (SR-IOV) lets a single physical NIC
expose multiple virtual functions (VFs) directly to containers,
bypassing the hypervisor's networking stack. The kernel-bypass HFT
path benefits from SR-IOV because the VF is a hardware queue with
direct access to the NIC.

This module discovers SR-IOV-capable interfaces via the standard
``/sys/class/net/<iface>/device/sriov_*`` sysfs entries. Used by:

- The operator's validating webhook (Phase 8) — reject HFT bots
  whose pods land on nodes without SR-IOV available.
- The Pod's startup probe — verifies the expected VF is bound.

Typical SR-IOV NICs in HFT: Intel I210, Intel X710, Mellanox ConnectX-5,
ConnectX-6, ConnectX-7.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


_NET_BASE = Path("/sys/class/net")


@dataclass(slots=True)
class SrIovDevice:
    """One SR-IOV-capable network interface."""

    iface: str
    totalvfs: int
    numvfs: int
    driver: str = ""
    vf_addresses: list[str] = field(default_factory=list)


def list_sr_iov_devices() -> list[SrIovDevice]:
    """Discover every SR-IOV-capable interface on the host."""
    if sys.platform != "linux" or not _NET_BASE.exists():
        return []
    out: list[SrIovDevice] = []
    for iface_path in sorted(_NET_BASE.iterdir()):
        if not iface_path.is_dir():
            continue
        device_dir = iface_path / "device"
        totalvfs_path = device_dir / "sriov_totalvfs"
        if not totalvfs_path.exists():
            continue
        try:
            totalvfs = int(totalvfs_path.read_text().strip())
        except (OSError, ValueError):
            continue
        numvfs = 0
        numvfs_path = device_dir / "sriov_numvfs"
        if numvfs_path.exists():
            try:
                numvfs = int(numvfs_path.read_text().strip())
            except (OSError, ValueError):
                pass
        driver = ""
        driver_link = device_dir / "driver"
        if driver_link.is_symlink() or driver_link.exists():
            try:
                driver = driver_link.resolve().name
            except OSError:
                pass
        vf_addresses: list[str] = []
        for vf_dir in sorted(device_dir.glob("virtfn*")):
            try:
                vf_addresses.append(vf_dir.resolve().name)
            except OSError:
                continue
        out.append(
            SrIovDevice(
                iface=iface_path.name,
                totalvfs=totalvfs,
                numvfs=numvfs,
                driver=driver,
                vf_addresses=vf_addresses,
            )
        )
    return out


def sr_iov_available() -> bool:
    """Return True iff at least one SR-IOV-capable interface exists."""
    return bool(list_sr_iov_devices())


__all__ = ["SrIovDevice", "list_sr_iov_devices", "sr_iov_available"]
