"""KubernetesAdapter ABC — pure abstract, no auto-registration.

This is the dependency-free version of ``aqp/kubernetes/protocol.py``.
Concrete adapters (``InClusterAdapter``, ``LocalComposeAdapter``,
``RpiClusterAdapter`` in ``aqp/``; ``KubernetesProvider`` in
``aqp_control_plane/``) inherit from this and either implement or
explicitly raise :class:`KubernetesAdapterUnavailable` for methods
they cannot service.

The ``aqp/`` version extends this with metaclass-driven registration
into ``aqp.core.registry``; the control-plane version does not need
that — it uses an explicit registry via
:mod:`aqp_platform_core.providers`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator

from aqp_platform_core.kubernetes.errors import KubernetesAdapterUnavailable
from aqp_platform_core.kubernetes.types import PodExecResult, PodInfo, PodLogEvent


class KubernetesAdapter(ABC):
    """Pluggable adapter for the cluster-side surface AQP needs."""

    # --- Status -------------------------------------------------------

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` when the adapter can service real calls."""

    def describe(self) -> dict[str, Any]:
        """JSON-friendly summary for diagnostics endpoints."""
        return {
            "class": self.__class__.__name__,
            "available": bool(self.is_available()),
        }

    # --- Generic ops --------------------------------------------------

    def scale_deployment(
        self, *, namespace: str, name: str, replicas: int
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support scale_deployment"
        )

    def pod_logs(
        self, *, namespace: str, name: str, tail_lines: int = 200
    ) -> str:
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support pod_logs"
        )

    def apply_manifest(
        self, *, manifest: dict[str, Any], namespace: str | None = None
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support apply_manifest"
        )

    # --- Pod-level ops ------------------------------------------------

    def list_pods(
        self,
        *,
        namespace: str,
        label_selector: str | None = None,
    ) -> list[PodInfo]:
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support list_pods"
        )

    def exec_in_pod(
        self,
        *,
        namespace: str,
        name: str,
        command: list[str],
        container: str | None = None,
        timeout_seconds: int = 60,
        stdin: bytes | None = None,
    ) -> PodExecResult:
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support exec_in_pod"
        )

    def stream_pod_logs(
        self,
        *,
        namespace: str,
        name: str,
        container: str | None = None,
        since_seconds: int | None = None,
        tail_lines: int | None = None,
        follow: bool = True,
        max_lines: int | None = None,
    ) -> Iterator[PodLogEvent]:
        """Yield log frames; never block the caller.

        Implementations MUST use ``_preload_content=False`` on
        ``read_namespaced_pod_log`` and consume via
        ``kubernetes.watch.Watch().stream(...)`` — the synchronous
        ``follow=True`` path hangs on sparse log emission (documented
        client bug).
        """
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support stream_pod_logs"
        )

    def get_pod_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        container: str | None = None,
    ) -> bytes:
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support get_pod_archive"
        )

    def put_pod_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        data: bytes,
        container: str | None = None,
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable(
            f"{self.__class__.__name__} does not support put_pod_archive"
        )


__all__ = ["KubernetesAdapter"]
