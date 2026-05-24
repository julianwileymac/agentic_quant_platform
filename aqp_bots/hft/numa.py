"""NUMA topology discovery and pinning helpers.

HFT bots run on dedicated nodes with kubelet ``topologyManagerPolicy:
single-numa-node`` so the Pod's CPU + memory are restricted to one
NUMA domain. This module:

1. Discovers the NUMA topology via ``/sys/devices/system/node/*``.
2. Exposes :func:`pin_to_node` for processes that need to set
   ``sched_setaffinity`` themselves (e.g. the bot's exporter thread).
3. Provides :class:`NumaPinHint` for the operator to emit Pod-level
   affinity / nodeSelector annotations.

Linux-only; on macOS / Windows the helpers degrade to no-ops so the
package still imports in dev.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


_NODE_BASE = Path("/sys/devices/system/node")


@dataclass(slots=True)
class NumaNode:
    """One NUMA node."""

    node_id: int
    cpu_list: list[int] = field(default_factory=list)
    memory_total_kb: int = 0


@dataclass(slots=True)
class NumaTopology:
    """Discovered NUMA topology for the local host."""

    nodes: list[NumaNode] = field(default_factory=list)
    available: bool = False

    def node_for_cpu(self, cpu: int) -> int | None:
        for node in self.nodes:
            if cpu in node.cpu_list:
                return node.node_id
        return None


@dataclass(slots=True)
class NumaPinHint:
    """K8s-friendly pinning hints derived from the topology."""

    preferred_node: int | None = None
    cpu_count: int = 1
    requires_topology_manager: bool = True
    requires_single_numa: bool = True


def discover_topology() -> NumaTopology:
    """Read /sys/devices/system/node/* and build a topology."""
    if sys.platform != "linux" or not _NODE_BASE.exists():
        return NumaTopology(available=False)
    topo = NumaTopology(available=True)
    for node_dir in sorted(_NODE_BASE.glob("node*")):
        try:
            node_id = int(node_dir.name.removeprefix("node"))
        except ValueError:
            continue
        cpu_list: list[int] = []
        try:
            spec = (node_dir / "cpulist").read_text().strip()
            for chunk in spec.split(","):
                chunk = chunk.strip()
                if "-" in chunk:
                    lo, hi = chunk.split("-", 1)
                    cpu_list.extend(range(int(lo), int(hi) + 1))
                elif chunk:
                    cpu_list.append(int(chunk))
        except (OSError, ValueError):
            pass
        topo.nodes.append(NumaNode(node_id=node_id, cpu_list=cpu_list))
    return topo


def pin_to_node(node_id: int) -> bool:
    """Pin the current process's CPU affinity to node_id.

    Returns True on success.  Requires CAP_SYS_NICE or root.
    """
    topo = discover_topology()
    target = next((n for n in topo.nodes if n.node_id == node_id), None)
    if target is None or not target.cpu_list:
        return False
    try:
        os.sched_setaffinity(0, set(target.cpu_list))  # type: ignore[attr-defined]
        return True
    except (AttributeError, OSError):
        return False


__all__ = [
    "NumaNode",
    "NumaPinHint",
    "NumaTopology",
    "discover_topology",
    "pin_to_node",
]
