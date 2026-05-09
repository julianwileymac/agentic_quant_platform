"""In-cluster / kubeconfig adapter using the official Kubernetes Python SDK.

Loaded when AQP runs inside a cluster (pod-internal `ServiceAccount`)
or has a local `KUBECONFIG`. The `kubernetes` Python dependency is
optional — when missing, :meth:`is_available` returns ``False`` so
routes degrade gracefully.

This adapter implements only the operations AQP actually uses today
(``scale_deployment``, ``pod_logs``, ``apply_manifest``); Kafka /
Flink go through the rpi management adapter or native admin clients
that already exist under :mod:`aqp.streaming.admin`. Adding more
in-cluster ops here is straightforward — call the relevant
``CoreV1Api`` / ``CustomObjectsApi`` method.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.kubernetes.protocol import (
    KubernetesAdapter,
    KubernetesAdapterError,
    KubernetesAdapterUnavailable,
)

logger = logging.getLogger(__name__)


class InClusterAdapter(KubernetesAdapter):
    """Direct K8s API access via the kubernetes-client SDK."""

    adapter_kind = "in_cluster"
    adapter_alias = "InClusterAdapter"

    def __init__(self) -> None:
        self._loaded = False
        self._k8s_module = None
        try:
            self._load_config()
        except Exception as exc:  # noqa: BLE001
            logger.debug("InClusterAdapter unavailable: %s", exc)

    def _load_config(self) -> None:
        try:
            import kubernetes as k8s  # type: ignore
        except ImportError:
            self._loaded = False
            return
        try:
            k8s.config.load_incluster_config()
            self._loaded = True
            self._k8s_module = k8s
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            k8s.config.load_kube_config()
            self._loaded = True
            self._k8s_module = k8s
        except Exception as exc:  # noqa: BLE001
            logger.debug("kubeconfig load failed: %s", exc)
            self._loaded = False

    def is_available(self) -> bool:
        return bool(self._loaded)

    # ------------------------------------------------------------------
    # Generic ops (the ones AQP needs today)
    # ------------------------------------------------------------------

    def scale_deployment(
        self, *, namespace: str, name: str, replicas: int
    ) -> dict[str, Any]:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            apps_v1 = self._k8s_module.client.AppsV1Api()  # type: ignore[union-attr]
            scale = apps_v1.read_namespaced_deployment_scale(name=name, namespace=namespace)
            scale.spec.replicas = int(replicas)
            updated = apps_v1.replace_namespaced_deployment_scale(
                name=name, namespace=namespace, body=scale
            )
            return {
                "name": name,
                "namespace": namespace,
                "replicas": int(getattr(updated.spec, "replicas", replicas)),
            }
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"scale_deployment failed: {exc}") from exc

    def pod_logs(
        self, *, namespace: str, name: str, tail_lines: int = 200
    ) -> str:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            core_v1 = self._k8s_module.client.CoreV1Api()  # type: ignore[union-attr]
            return str(
                core_v1.read_namespaced_pod_log(
                    name=name,
                    namespace=namespace,
                    tail_lines=int(tail_lines),
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"pod_logs failed: {exc}") from exc

    def apply_manifest(
        self, *, manifest: dict[str, Any], namespace: str | None = None
    ) -> dict[str, Any]:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            from kubernetes.utils import create_from_dict  # type: ignore

            api_client = self._k8s_module.client.ApiClient()  # type: ignore[union-attr]
            results = create_from_dict(api_client, manifest, namespace=namespace)
            return {
                "applied": True,
                "kinds": [str(r.__class__.__name__) for r in results],
            }
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"apply_manifest failed: {exc}") from exc


__all__ = ["InClusterAdapter"]
