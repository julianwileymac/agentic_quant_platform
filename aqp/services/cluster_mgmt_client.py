"""HTTP client for the deprecated rpi-k8s-management API (rollback only).

DEPRECATED. The canonical admin surface is
:class:`aqp.services.control_plane_client.AQPControlPlaneClient`
talking to ``aqp_control_plane`` (``/manage/streaming/*``,
``/manage/observability/*``, ``/manage/lakehouse/*``,
``/manage/timeseries/*``, ``/manage/data-plane/*``).

After the rpi <-> AQP decoupling this client is **rollback-only**:

- The matching cluster Deployment (``rpi-k8s-management``) is pinned
  to a ``:v1-final`` image under
  ``aqp_platform/deployments/kubernetes/rollback/legacy-management/`` and is **not**
  applied by the default cluster bootstrap.
- ``settings.control_plane_legacy_fallback`` defaults to ``False``;
  constructing a :class:`ClusterMgmtClient` while the flag is False
  raises :class:`ClusterMgmtError`. To re-enable the legacy path
  during an emergency rollback, set
  ``AQP_CONTROL_PLANE_LEGACY_FALLBACK=true`` on the API / worker
  ConfigMap and re-apply the legacy-management kustomization.

The native Kafka / Flink admin in :mod:`aqp.streaming.admin` and the
``/manage/streaming/*`` routes in ``aqp_control_plane`` are the
preferred paths.
"""
from __future__ import annotations

import logging
import warnings
from typing import Any

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


class ClusterMgmtError(RuntimeError):
    """Raised when the cluster management API responds with an error."""


def _emit_deprecation_warning_once() -> None:
    """Soft deprecation warning. Logged once per process."""
    if getattr(_emit_deprecation_warning_once, "_emitted", False):
        return
    _emit_deprecation_warning_once._emitted = True  # type: ignore[attr-defined]
    warnings.warn(
        "aqp.services.cluster_mgmt_client.ClusterMgmtClient is "
        "deprecated and rollback-only. Route every new call through "
        "aqp.services.control_plane_client.AQPControlPlaneClient.",
        DeprecationWarning,
        stacklevel=3,
    )


class ClusterMgmtClient:
    """Legacy HTTP client for the deprecated rpi-k8s-management API.

    Rollback-only. Refuses to instantiate unless
    ``settings.control_plane_legacy_fallback`` is True.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        if not getattr(settings, "control_plane_legacy_fallback", False):
            raise ClusterMgmtError(
                "ClusterMgmtClient is rollback-only and the legacy "
                "fallback is disabled. Either set "
                "AQP_CONTROL_PLANE_LEGACY_FALLBACK=true (emergency "
                "rollback) or migrate the call site to "
                "aqp.services.control_plane_client.AQPControlPlaneClient."
            )
        _emit_deprecation_warning_once()
        url = base_url or getattr(settings, "cluster_mgmt_url", "") or ""
        self._base = url.rstrip("/")
        self._token = token or getattr(settings, "cluster_mgmt_token", None) or ""
        self._timeout = float(timeout_s)

    @property
    def configured(self) -> bool:
        return bool(self._base)

    def _client(self) -> httpx.Client:
        headers: dict[str, str] = {"User-Agent": "aqp-cluster-mgmt-client"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.Client(timeout=self._timeout, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        if not self.configured:
            raise ClusterMgmtError("cluster_mgmt_url not configured")
        url = f"{self._base}/api{path}"
        with self._client() as client:
            try:
                r = client.request(method, url, params=params, json=json_body)
            except Exception as exc:  # noqa: BLE001
                raise ClusterMgmtError(f"cluster mgmt unreachable: {exc}") from exc
            if r.status_code == 204:
                return None
            if r.status_code >= 400:
                detail = r.text or r.reason_phrase
                raise ClusterMgmtError(f"{method} {url}: {r.status_code} {detail}")
            try:
                return r.json()
            except ValueError:
                return r.text

    # --------- kafka -----------------------------------------------------
    def kafka_topics(self) -> list[dict[str, Any]]:
        return self._request("GET", "/kafka/topics") or []

    def kafka_topic(self, name: str) -> dict[str, Any]:
        return self._request("GET", f"/kafka/topics/{name}")

    def kafka_create_topic(
        self,
        *,
        name: str,
        partitions: int,
        replication_factor: int,
        config: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/kafka/topics",
            json_body={
                "name": name,
                "partitions": partitions,
                "replication_factor": replication_factor,
                "config": dict(config or {}),
            },
        )

    def kafka_delete_topic(self, name: str) -> None:
        self._request("DELETE", f"/kafka/topics/{name}")

    def kafka_consumer_groups(self) -> list[dict[str, Any]]:
        return self._request("GET", "/kafka/consumer-groups") or []

    def kafka_users(self) -> list[dict[str, Any]]:
        return self._request("GET", "/kafka/users") or []

    def kafka_create_user(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/kafka/users", json_body=body)

    def kafka_delete_user(self, name: str) -> None:
        self._request("DELETE", f"/kafka/users/{name}")

    def kafka_user_secret(self, name: str) -> dict[str, Any]:
        return self._request("GET", f"/kafka/users/{name}/secret")

    def kafka_connectors(self) -> list[dict[str, Any]]:
        return self._request("GET", "/kafka/connectors") or []

    def kafka_patch_connector(self, name: str, state: str) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/kafka/connectors/{name}/state",
            params={"state": state},
        )

    def kafka_schema_subjects(self) -> list[dict[str, Any]]:
        return self._request("GET", "/kafka/schema-registry/subjects") or []

    def kafka_produce(self, *, topic: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/kafka/topics/{topic}/produce",
            json_body={"records": list(records)},
        )

    # --------- flink -----------------------------------------------------
    def flink_deployments(self) -> list[dict[str, Any]]:
        return self._request("GET", "/flink/deployments") or []

    def flink_session_jobs(self, namespace: str | None = None) -> list[dict[str, Any]]:
        params = {"namespace": namespace} if namespace else None
        return self._request("GET", "/flink/sessionjobs", params=params) or []

    def flink_session_job(self, name: str, namespace: str | None = None) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._request("GET", f"/flink/sessionjobs/{name}", params=params)

    def flink_create_session_job(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/flink/sessionjobs", json_body=body)

    def flink_patch_session_job(
        self,
        name: str,
        patch: dict[str, Any],
        namespace: str | None = None,
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._request(
            "PATCH",
            f"/flink/sessionjobs/{name}",
            params=params,
            json_body=patch,
        )

    def flink_delete_session_job(self, name: str, namespace: str | None = None) -> None:
        params = {"namespace": namespace} if namespace else None
        self._request("DELETE", f"/flink/sessionjobs/{name}", params=params)

    def flink_activate_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._request(
            "POST",
            f"/flink/sessionjobs/{name}/activate",
            params=params,
        )

    def flink_suspend_session_job(
        self, name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._request(
            "POST",
            f"/flink/sessionjobs/{name}/suspend",
            params=params,
        )

    def flink_scale_session_job(
        self,
        name: str,
        *,
        parallelism: int,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"parallelism": parallelism}
        if namespace:
            params["namespace"] = namespace
        return self._request(
            "POST",
            f"/flink/sessionjobs/{name}/scale",
            params=params,
        )

    def flink_savepoint(self, name: str) -> dict[str, Any]:
        return self._request("POST", f"/flink/sessionjobs/{name}/savepoint")

    def flink_jobs(self) -> list[dict[str, Any]]:
        return self._request("GET", "/flink/jobs") or []

    def flink_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/flink/jobs/{job_id}")

    # --------- alpha vantage producer ----------------------------------
    def alphavantage_stream(self, *, enable: bool, replicas: int = 1) -> dict[str, Any]:
        return self._request(
            "POST",
            "/alphavantage/stream",
            json_body={"enable": enable, "replicas": replicas},
        )

    def alphavantage_health(self) -> dict[str, Any]:
        return self._request("GET", "/alphavantage/health")

    def alphavantage_usage(self) -> dict[str, Any]:
        return self._request("GET", "/alphavantage/usage")

    # --------- generic deployment patches (custom producers) -----------
    def k8s_scale_deployment(
        self, *, namespace: str, name: str, replicas: int
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/deployments/{namespace}/{name}/scale",
            params={"replicas": replicas},
        )

    # --------- pod-level ops (Phase 1) ---------------------------------
    def list_pods(
        self, *, namespace: str, label_selector: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if label_selector:
            params["label_selector"] = label_selector
        return self._request(
            "GET", f"/pods/{namespace}", params=params or None
        ) or []

    def pod_exec(
        self,
        *,
        namespace: str,
        name: str,
        command: list[str],
        container: str | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "command": list(command),
            "timeout_seconds": int(timeout_seconds),
        }
        if container:
            body["container"] = container
        return self._request(
            "POST",
            f"/pods/{namespace}/{name}/exec",
            json_body=body,
        )

    def pod_logs_stream(
        self,
        *,
        namespace: str,
        name: str,
        container: str | None = None,
        since_seconds: int | None = None,
        tail_lines: int | None = None,
        follow: bool = True,
        max_lines: int | None = None,
    ) -> list[dict[str, Any]]:
        """Batch the management API's log frames into a list.

        The rpi management API exposes a WebSocket for true streaming;
        the HTTP fallback here returns a bounded batch so AQP can
        forward the frames to its own WebSocket consumers (the
        ``/cluster/pods/{ns}/{name}/logs/stream`` route on the AQP
        side). For a true streaming proxy, attach to the management
        WebSocket directly from the adapter — left as a future
        extension.
        """
        params: dict[str, Any] = {"follow": "true" if follow else "false"}
        if container:
            params["container"] = container
        if since_seconds is not None:
            params["since_seconds"] = int(since_seconds)
        if tail_lines is not None:
            params["tail_lines"] = int(tail_lines)
        if max_lines is not None:
            params["max_lines"] = int(max_lines)
        return self._request(
            "GET",
            f"/pods/{namespace}/{name}/logs",
            params=params,
        ) or []

    def pod_get_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        container: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"path": path}
        if container:
            params["container"] = container
        return self._request(
            "GET",
            f"/pods/{namespace}/{name}/archive",
            params=params,
        )

    def pod_put_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        data_b64: str,
        container: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"path": path, "data_b64": data_b64}
        if container:
            body["container"] = container
        return self._request(
            "POST",
            f"/pods/{namespace}/{name}/archive",
            json_body=body,
        )


_singleton: ClusterMgmtClient | None = None


def get_cluster_mgmt_client() -> ClusterMgmtClient:
    global _singleton
    if _singleton is None:
        _singleton = ClusterMgmtClient()
    return _singleton


__all__ = ["ClusterMgmtClient", "ClusterMgmtError", "get_cluster_mgmt_client"]
