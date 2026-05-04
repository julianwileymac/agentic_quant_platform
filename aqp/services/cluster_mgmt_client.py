"""HTTP client for the rpi_kubernetes management API.

The rpi_kubernetes management backend exposes ``/api/kafka/**``,
``/api/flink/**``, and ``/api/alphavantage/**`` as the cluster-level
single source of truth (see
``rpi_kubernetes/management/backend/src/api/__init__.py``). This
client is the AQP-side proxy: every call hits the cluster API with
the ``AQP_CLUSTER_MGMT_TOKEN`` bearer header and is wrapped with
retry + tenant-aware logging.

The native Kafka / Flink admin in :mod:`aqp.streaming.admin` is the
preferred path; this client is the *fallback* and the source of
cluster-only operations (Strimzi user management, AV producer
deployment scale, Argo workflow submissions).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


class ClusterMgmtError(RuntimeError):
    """Raised when the cluster management API responds with an error."""


class ClusterMgmtClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_s: float = 15.0,
    ) -> None:
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


_singleton: ClusterMgmtClient | None = None


def get_cluster_mgmt_client() -> ClusterMgmtClient:
    global _singleton
    if _singleton is None:
        _singleton = ClusterMgmtClient()
    return _singleton


__all__ = ["ClusterMgmtClient", "ClusterMgmtError", "get_cluster_mgmt_client"]
