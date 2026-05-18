"""Concrete :class:`aqp.kubernetes.KubernetesAdapter` implementations."""
from __future__ import annotations

from aqp.kubernetes.adapters.in_cluster import InClusterAdapter
from aqp.kubernetes.adapters.local_compose import LocalComposeAdapter
from aqp.kubernetes.adapters.none import NoneAdapter
from aqp.kubernetes.adapters.rpi_cluster import RpiClusterAdapter

# Cloud adapter imports are wrapped in try/except so missing optional
# cloud SDKs do not block AQP from booting in a "local" deployment.
try:  # pragma: no cover - dep guard
    from aqp.kubernetes.adapters.aws_eks import AwsEksAdapter  # noqa: F401
except Exception:  # noqa: BLE001
    AwsEksAdapter = None  # type: ignore[assignment]
try:  # pragma: no cover - dep guard
    from aqp.kubernetes.adapters.gcp_gke import GcpGkeAdapter  # noqa: F401
except Exception:  # noqa: BLE001
    GcpGkeAdapter = None  # type: ignore[assignment]
try:  # pragma: no cover - dep guard
    from aqp.kubernetes.adapters.azure_aks import AzureAksAdapter  # noqa: F401
except Exception:  # noqa: BLE001
    AzureAksAdapter = None  # type: ignore[assignment]

__all__ = [
    "AwsEksAdapter",
    "AzureAksAdapter",
    "GcpGkeAdapter",
    "InClusterAdapter",
    "LocalComposeAdapter",
    "NoneAdapter",
    "RpiClusterAdapter",
]
