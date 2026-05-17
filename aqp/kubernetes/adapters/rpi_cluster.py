"""rpi_kubernetes adapter — wraps the existing :class:`ClusterMgmtClient`.

Activated when ``settings.cluster_mgmt_url`` is set. Every call
forwards to the underlying HTTP client; failures become
:class:`KubernetesAdapterError` (or
:class:`KubernetesAdapterUnavailable` when the URL is empty) so routes
can return clean status codes.

This is the only place in AQP that is allowed to import
:class:`aqp.services.cluster_mgmt_client.ClusterMgmtClient` directly.
All other code reaches the cluster through
:func:`aqp.kubernetes.get_kubernetes_adapter`.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from aqp.kubernetes.protocol import (
    KubernetesAdapter,
    KubernetesAdapterError,
    KubernetesAdapterUnavailable,
    PodExecResult,
    PodInfo,
    PodLogEvent,
)

logger = logging.getLogger(__name__)


class RpiClusterAdapter(KubernetesAdapter):
    """Forwards to ``rpi_kubernetes/management/backend`` via HTTP."""

    adapter_kind = "rpi_cluster"
    adapter_alias = "RpiClusterAdapter"

    def __init__(self, client: Any | None = None) -> None:
        # Lazy import keeps startup fast and avoids dragging the
        # cluster-mgmt client into ``NoneAdapter`` deployments.
        from aqp.services.cluster_mgmt_client import (
            ClusterMgmtClient,
            ClusterMgmtError,
        )

        self._client_factory = ClusterMgmtClient
        self._explicit_client = client
        self._error_class = ClusterMgmtError

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        client = self._fresh_client()
        return bool(getattr(client, "configured", False))

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _fresh_client(self) -> Any:
        """Return either the explicit injected client or a freshly-built one.

        Building per call is cheap (just reads settings + assembles a
        small dataclass) and avoids the "stale URL across tests" issue
        without coupling the adapter cache to settings mutations.
        """
        if self._explicit_client is not None:
            return self._explicit_client
        return self._client_factory()

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        client = self._fresh_client()
        if not bool(getattr(client, "configured", False)):
            raise KubernetesAdapterUnavailable(
                "rpi cluster adapter not configured (set AQP_CLUSTER_MGMT_URL)"
            )
        method = getattr(client, method_name)
        try:
            return method(*args, **kwargs)
        except self._error_class as exc:
            raise KubernetesAdapterError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Generic ops
    # ------------------------------------------------------------------

    def scale_deployment(
        self, *, namespace: str, name: str, replicas: int
    ) -> dict[str, Any]:
        return self._call(
            "k8s_scale_deployment",
            namespace=namespace,
            name=name,
            replicas=replicas,
        )

    # ------------------------------------------------------------------
    # Kafka
    # ------------------------------------------------------------------

    def kafka_topics(self) -> list[dict[str, Any]]:
        return self._call("kafka_topics")

    def kafka_topic(self, name: str) -> dict[str, Any]:
        return self._call("kafka_topic", name)

    def kafka_create_topic(
        self,
        *,
        name: str,
        partitions: int,
        replication_factor: int,
        config: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._call(
            "kafka_create_topic",
            name=name,
            partitions=partitions,
            replication_factor=replication_factor,
            config=config,
        )

    def kafka_delete_topic(self, name: str) -> None:
        self._call("kafka_delete_topic", name)

    def kafka_consumer_groups(self) -> list[dict[str, Any]]:
        return self._call("kafka_consumer_groups")

    def kafka_users(self) -> list[dict[str, Any]]:
        return self._call("kafka_users")

    def kafka_create_user(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._call("kafka_create_user", body)

    def kafka_delete_user(self, name: str) -> None:
        self._call("kafka_delete_user", name)

    def kafka_user_secret(self, name: str) -> dict[str, Any]:
        return self._call("kafka_user_secret", name)

    def kafka_connectors(self) -> list[dict[str, Any]]:
        return self._call("kafka_connectors")

    def kafka_patch_connector(self, name: str, state: str) -> dict[str, Any]:
        return self._call("kafka_patch_connector", name, state)

    def kafka_schema_subjects(self) -> list[dict[str, Any]]:
        return self._call("kafka_schema_subjects")

    def kafka_produce(
        self, *, topic: str, records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self._call("kafka_produce", topic=topic, records=records)

    # ------------------------------------------------------------------
    # Flink
    # ------------------------------------------------------------------

    def flink_deployments(self) -> list[dict[str, Any]]:
        return self._call("flink_deployments")

    def flink_session_jobs(self, namespace: str | None = None) -> list[dict[str, Any]]:
        return self._call("flink_session_jobs", namespace)

    def flink_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        return self._call("flink_session_job", name, namespace)

    def flink_create_session_job(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._call("flink_create_session_job", body)

    def flink_patch_session_job(
        self,
        name: str,
        patch: dict[str, Any],
        namespace: str | None = None,
    ) -> dict[str, Any]:
        return self._call("flink_patch_session_job", name, patch, namespace)

    def flink_delete_session_job(
        self, name: str, namespace: str | None = None
    ) -> None:
        self._call("flink_delete_session_job", name, namespace)

    def flink_activate_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        return self._call("flink_activate_session_job", name, namespace)

    def flink_suspend_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        return self._call("flink_suspend_session_job", name, namespace)

    def flink_scale_session_job(
        self,
        name: str,
        *,
        parallelism: int,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        return self._call(
            "flink_scale_session_job",
            name,
            parallelism=parallelism,
            namespace=namespace,
        )

    def flink_savepoint(self, name: str) -> dict[str, Any]:
        return self._call("flink_savepoint", name)

    def flink_jobs(self) -> list[dict[str, Any]]:
        return self._call("flink_jobs")

    def flink_job(self, job_id: str) -> dict[str, Any]:
        return self._call("flink_job", job_id)

    # ------------------------------------------------------------------
    # AlphaVantage stream / health
    # ------------------------------------------------------------------

    def alphavantage_stream(
        self, *, enable: bool, replicas: int = 1
    ) -> dict[str, Any]:
        return self._call("alphavantage_stream", enable=enable, replicas=replicas)

    def alphavantage_health(self) -> dict[str, Any]:
        return self._call("alphavantage_health")

    def alphavantage_usage(self) -> dict[str, Any]:
        return self._call("alphavantage_usage")

    # ------------------------------------------------------------------
    # Phase 1 — pod-level ops (proxied through the management API)
    # ------------------------------------------------------------------

    def list_pods(
        self,
        *,
        namespace: str,
        label_selector: str | None = None,
    ) -> list[PodInfo]:
        rows = self._call("list_pods", namespace=namespace, label_selector=label_selector)
        out: list[PodInfo] = []
        for row in rows or []:
            try:
                out.append(
                    PodInfo(
                        namespace=str(row.get("namespace", namespace)),
                        name=str(row.get("name", "")),
                        phase=str(row.get("phase", "") or ""),
                        node=str(row.get("node", "") or ""),
                        pod_ip=str(row.get("pod_ip", "") or ""),
                        started_at=str(row.get("started_at", "") or ""),
                        containers=[str(c) for c in (row.get("containers") or [])],
                        labels={
                            str(k): str(v) for k, v in (row.get("labels") or {}).items()
                        },
                    )
                )
            except Exception:  # noqa: BLE001
                logger.debug("list_pods: skipping malformed row", exc_info=True)
        return out

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
        if stdin is not None:
            raise KubernetesAdapterError(
                "rpi_cluster adapter does not support exec_in_pod stdin"
            )
        payload = self._call(
            "pod_exec",
            namespace=namespace,
            name=name,
            command=list(command),
            container=container,
            timeout_seconds=int(timeout_seconds),
        )
        return PodExecResult(
            namespace=namespace,
            name=name,
            container=container,
            command=list(command),
            stdout=str(payload.get("stdout", "")) if isinstance(payload, dict) else "",
            stderr=str(payload.get("stderr", "")) if isinstance(payload, dict) else "",
            returncode=(
                int(payload.get("returncode"))
                if isinstance(payload, dict) and payload.get("returncode") is not None
                else None
            ),
            elapsed_ms=(
                float(payload.get("elapsed_ms"))
                if isinstance(payload, dict) and payload.get("elapsed_ms") is not None
                else None
            ),
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
        events = self._call(
            "pod_logs_stream",
            namespace=namespace,
            name=name,
            container=container,
            since_seconds=since_seconds,
            tail_lines=tail_lines,
            follow=bool(follow),
            max_lines=max_lines,
        )
        for ev in events or []:
            try:
                yield PodLogEvent(
                    namespace=str(ev.get("namespace", namespace)),
                    name=str(ev.get("name", name)),
                    container=ev.get("container") or container,
                    line=str(ev.get("line", "")),
                    timestamp=str(ev.get("timestamp", "") or ""),
                    source=str(ev.get("source", "stdout") or "stdout"),
                )
            except Exception:  # noqa: BLE001
                logger.debug("stream_pod_logs: skipping malformed event", exc_info=True)

    def get_pod_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        container: str | None = None,
    ) -> bytes:
        payload = self._call(
            "pod_get_archive",
            namespace=namespace,
            name=name,
            path=path,
            container=container,
        )
        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload)
        if isinstance(payload, str):
            # The proxy returns base64-encoded tar bytes by default.
            try:
                import base64

                return base64.b64decode(payload)
            except Exception as exc:  # noqa: BLE001
                raise KubernetesAdapterError(
                    f"pod_get_archive returned non-base64 payload: {exc}"
                ) from exc
        if isinstance(payload, dict) and payload.get("data"):
            try:
                import base64

                return base64.b64decode(str(payload["data"]))
            except Exception as exc:  # noqa: BLE001
                raise KubernetesAdapterError(
                    f"pod_get_archive returned malformed payload: {exc}"
                ) from exc
        raise KubernetesAdapterError("pod_get_archive returned empty payload")

    def put_pod_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        data: bytes,
        container: str | None = None,
    ) -> dict[str, Any]:
        import base64

        encoded = base64.b64encode(bytes(data)).decode("ascii")
        return self._call(
            "pod_put_archive",
            namespace=namespace,
            name=name,
            path=path,
            container=container,
            data_b64=encoded,
        )


__all__ = ["RpiClusterAdapter"]
