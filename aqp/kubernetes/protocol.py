"""KubernetesAdapter ABC + auto-registering metaclass.

Mirrors :class:`aqp.credentials.protocol.SecretStoreMeta` and
:class:`aqp.auth.providers.protocol.IdentityProviderMeta`: subclasses
set ``adapter_kind`` (``none``, ``rpi_cluster``, ``in_cluster``,
``local_compose``) and the metaclass calls
:func:`aqp.core.registry.register` automatically.

The ABC defines a small "what does the cluster expose?" surface plus a
deliberately-conservative set of methods the existing AQP code needs
(``kafka_*``, ``flink_*``, ``alphavantage_*``, ``scale_deployment``,
``apply_manifest``, ``pod_logs``). Adapters opt out of methods they
can't implement by raising :class:`KubernetesAdapterUnavailable`; the
calling routes translate that to ``HTTP 503``.
"""
from __future__ import annotations

import logging
import threading
from abc import ABCMeta, abstractmethod
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


K8S_ADAPTER_KIND = "k8s_adapter"


class KubernetesAdapterError(RuntimeError):
    """Base class for adapter-side failures (HTTP errors, kubeconfig)."""


class KubernetesAdapterUnavailable(KubernetesAdapterError):
    """Raised when an adapter cannot service a call.

    The :class:`NoneAdapter` raises this for every operation, and
    feature-incomplete adapters raise it for unsupported methods.
    Routes catch it and return 503.
    """


# ---------------------------------------------------------------------------
# Metaclass
# ---------------------------------------------------------------------------


class KubernetesAdapterMeta(ABCMeta):
    """Metaclass that auto-registers concrete :class:`KubernetesAdapter`."""

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_adapter__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        adapter_kind = getattr(cls, "adapter_kind", None)
        if not adapter_kind:
            return cls
        alias = getattr(cls, "adapter_alias", None) or cls.__name__
        try:
            register(name=alias, kind=K8S_ADAPTER_KIND, source=str(adapter_kind))(cls)
        except Exception:  # noqa: BLE001
            logger.debug("KubernetesAdapter auto-registration failed for %s", name, exc_info=True)
        return cls


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class KubernetesAdapter(metaclass=KubernetesAdapterMeta):
    """Pluggable adapter for the cluster-side surface AQP needs."""

    __abstract_adapter__: ClassVar[bool] = True

    adapter_kind: ClassVar[str] = ""
    adapter_alias: ClassVar[str | None] = None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` when the adapter can service real calls."""

    def describe(self) -> dict[str, Any]:
        """JSON-friendly summary for the diagnostics endpoint."""
        return {
            "kind": self.adapter_kind,
            "alias": self.adapter_alias or self.__class__.__name__,
            "available": bool(self.is_available()),
        }

    # ------------------------------------------------------------------
    # Generic ops
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Kafka (Strimzi-style admin API)
    # ------------------------------------------------------------------

    def kafka_topics(self) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("kafka_topics")

    def kafka_topic(self, name: str) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("kafka_topic")

    def kafka_create_topic(
        self,
        *,
        name: str,
        partitions: int,
        replication_factor: int,
        config: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("kafka_create_topic")

    def kafka_delete_topic(self, name: str) -> None:
        raise KubernetesAdapterUnavailable("kafka_delete_topic")

    def kafka_consumer_groups(self) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("kafka_consumer_groups")

    def kafka_users(self) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("kafka_users")

    def kafka_create_user(self, body: dict[str, Any]) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("kafka_create_user")

    def kafka_delete_user(self, name: str) -> None:
        raise KubernetesAdapterUnavailable("kafka_delete_user")

    def kafka_user_secret(self, name: str) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("kafka_user_secret")

    def kafka_connectors(self) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("kafka_connectors")

    def kafka_patch_connector(self, name: str, state: str) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("kafka_patch_connector")

    def kafka_schema_subjects(self) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("kafka_schema_subjects")

    def kafka_produce(self, *, topic: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("kafka_produce")

    # ------------------------------------------------------------------
    # Flink session jobs
    # ------------------------------------------------------------------

    def flink_deployments(self) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("flink_deployments")

    def flink_session_jobs(self, namespace: str | None = None) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("flink_session_jobs")

    def flink_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_session_job")

    def flink_create_session_job(self, body: dict[str, Any]) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_create_session_job")

    def flink_patch_session_job(
        self,
        name: str,
        patch: dict[str, Any],
        namespace: str | None = None,
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_patch_session_job")

    def flink_delete_session_job(
        self, name: str, namespace: str | None = None
    ) -> None:
        raise KubernetesAdapterUnavailable("flink_delete_session_job")

    def flink_activate_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_activate_session_job")

    def flink_suspend_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_suspend_session_job")

    def flink_scale_session_job(
        self,
        name: str,
        *,
        parallelism: int,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_scale_session_job")

    def flink_savepoint(self, name: str) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_savepoint")

    def flink_jobs(self) -> list[dict[str, Any]]:
        raise KubernetesAdapterUnavailable("flink_jobs")

    def flink_job(self, job_id: str) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("flink_job")

    # ------------------------------------------------------------------
    # AlphaVantage stream / health
    # ------------------------------------------------------------------

    def alphavantage_stream(
        self, *, enable: bool, replicas: int = 1
    ) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("alphavantage_stream")

    def alphavantage_health(self) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("alphavantage_health")

    def alphavantage_usage(self) -> dict[str, Any]:
        raise KubernetesAdapterUnavailable("alphavantage_usage")


# ---------------------------------------------------------------------------
# Singleton + selection
# ---------------------------------------------------------------------------


_ADAPTER: KubernetesAdapter | None = None
_ADAPTER_LOCK = threading.RLock()


def list_adapter_classes() -> dict[str, type[KubernetesAdapter]]:
    """Return ``{alias: class}`` for every registered adapter."""
    from aqp.core.registry import list_by_kind

    out: dict[str, type[KubernetesAdapter]] = {}
    for alias, cls in list_by_kind(K8S_ADAPTER_KIND).items():
        if isinstance(cls, type) and issubclass(cls, KubernetesAdapter):
            out[alias] = cls
    return out


def _select_adapter_class(kind: str) -> type[KubernetesAdapter]:
    classes = list_adapter_classes()
    for cls in classes.values():
        if str(getattr(cls, "adapter_kind", "")).lower() == kind.lower():
            return cls
    # Fall back to the no-op adapter so misconfigured deployments do
    # not crash on startup.
    for cls in classes.values():
        if str(getattr(cls, "adapter_kind", "")).lower() == "none":
            return cls
    raise KubernetesAdapterError(f"No KubernetesAdapter registered for kind={kind!r}")


def _build_active_adapter() -> KubernetesAdapter:
    try:
        from aqp.config import settings

        kind = (str(getattr(settings, "kubernetes_adapter", "") or "").strip().lower() or "")
        # Auto-promote: if rpi mgmt URL is set, use the rpi adapter
        # without requiring the operator to also set kubernetes_adapter.
        if not kind:
            if (str(getattr(settings, "cluster_mgmt_url", "") or "")).strip():
                kind = "rpi_cluster"
            else:
                kind = "none"
    except Exception:
        kind = "none"
    cls = _select_adapter_class(kind)
    return cls()


def get_kubernetes_adapter() -> KubernetesAdapter:
    """Return the process-wide active :class:`KubernetesAdapter`."""
    global _ADAPTER
    if _ADAPTER is None:
        with _ADAPTER_LOCK:
            if _ADAPTER is None:
                _ADAPTER = _build_active_adapter()
    return _ADAPTER


def register_adapter(adapter: KubernetesAdapter) -> None:
    """Replace the active adapter (used by tests + dynamic re-config)."""
    global _ADAPTER
    with _ADAPTER_LOCK:
        _ADAPTER = adapter


def reset_kubernetes_adapter() -> None:
    """Drop the active adapter so the next call rebuilds from settings."""
    global _ADAPTER
    with _ADAPTER_LOCK:
        _ADAPTER = None


__all__ = [
    "K8S_ADAPTER_KIND",
    "KubernetesAdapter",
    "KubernetesAdapterError",
    "KubernetesAdapterMeta",
    "KubernetesAdapterUnavailable",
    "get_kubernetes_adapter",
    "list_adapter_classes",
    "register_adapter",
    "reset_kubernetes_adapter",
]
