"""KubernetesAdapter ABC + value types.

The ABC is a pure abstract class — concrete adapters live in
``aqp/kubernetes/adapters/`` (in-cluster / local_compose / rpi_cluster)
and ``aqp_control_plane/src/aqp_cp/providers/kubernetes.py``
(provider-grade variant for the control plane).

Mirrors AGENTS rule 28 — all cluster-side ops go through a
KubernetesAdapter — without forcing every consumer to drag in the
``aqp.core.registry`` registration side effect.
"""
from __future__ import annotations

from aqp_platform_core.kubernetes.errors import (
    KubernetesAdapterError,
    KubernetesAdapterUnavailable,
)
from aqp_platform_core.kubernetes.protocol import KubernetesAdapter
from aqp_platform_core.kubernetes.types import (
    PodExecResult,
    PodInfo,
    PodLogEvent,
)

__all__ = [
    "KubernetesAdapter",
    "KubernetesAdapterError",
    "KubernetesAdapterUnavailable",
    "PodExecResult",
    "PodInfo",
    "PodLogEvent",
]
