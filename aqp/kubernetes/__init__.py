"""Pluggable Kubernetes-side adapter for AQP.

AQP can run fully standalone (no Kubernetes) or attached to one of
several Kubernetes control planes. This package defines the
:class:`KubernetesAdapter` ABC and the concrete adapters AQP ships
with:

- :class:`NoneAdapter` (default): every call returns
  :class:`KubernetesAdapterUnavailable` so routes degrade to 503; AQP
  works fine without any cluster.
- :class:`RpiClusterAdapter`: wraps the existing
  :mod:`aqp.services.cluster_mgmt_client` HTTP client; activated by
  ``AQP_CLUSTER_MGMT_URL`` (so the "rpi attach" stays optional).
- :class:`InClusterAdapter`: uses the official ``kubernetes`` Python
  SDK with ``load_incluster_config`` / ``load_kube_config`` for
  pod-internal or kubeconfig-based access.
- :class:`LocalComposeAdapter`: subprocess wrapper around
  ``docker compose ps / logs / restart`` for the local platform
  overlay (Milestone 5).

Concrete adapters self-register through :class:`KubernetesAdapterMeta`
in the ``"k8s_adapter"`` registry kind, mirroring the
:class:`aqp.rl.core.base.RLComponentMeta` pattern.

Selection is driven by ``settings.kubernetes_adapter``; legacy
``cluster_mgmt_url`` continues to work as the rpi adapter's input.
"""
from __future__ import annotations

from aqp.kubernetes.adapters.in_cluster import InClusterAdapter
from aqp.kubernetes.adapters.local_compose import LocalComposeAdapter
from aqp.kubernetes.adapters.none import NoneAdapter
from aqp.kubernetes.adapters.rpi_cluster import RpiClusterAdapter
from aqp.kubernetes.protocol import (
    K8S_ADAPTER_KIND,
    KubernetesAdapter,
    KubernetesAdapterError,
    KubernetesAdapterMeta,
    KubernetesAdapterUnavailable,
    PodExecResult,
    PodInfo,
    PodLogEvent,
    get_kubernetes_adapter,
    list_adapter_classes,
    register_adapter,
    reset_kubernetes_adapter,
)

__all__ = [
    "InClusterAdapter",
    "K8S_ADAPTER_KIND",
    "KubernetesAdapter",
    "KubernetesAdapterError",
    "KubernetesAdapterMeta",
    "KubernetesAdapterUnavailable",
    "LocalComposeAdapter",
    "NoneAdapter",
    "PodExecResult",
    "PodInfo",
    "PodLogEvent",
    "RpiClusterAdapter",
    "get_kubernetes_adapter",
    "list_adapter_classes",
    "register_adapter",
    "reset_kubernetes_adapter",
]
