"""Native Flink admin client.

Two surfaces are exposed:

- :class:`FlinkRestClient` — thin httpx wrapper around the Flink REST
  API for ``/jobs/overview``, ``/jobs/{id}``, ``/jobs/{id}/checkpoints``,
  ``/jobs/{id}/exceptions``, and ``POST /jobs/{id}/savepoints``.
- :class:`FlinkSessionJobK8s` — kubernetes client wrapper that
  CRUDs the ``flink.apache.org/v1beta1.FlinkSessionJob`` custom
  resources used by the cluster Flink Operator (matches the YAMLs at
  ``rpi_kubernetes/kubernetes/base-services/flink/jobs/*.yaml``).

Both classes degrade gracefully: missing SDKs raise
:class:`FlinkAdminUnavailableError` and the route module falls back
to the cluster-mgmt proxy.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


class FlinkAdminError(RuntimeError):
    """Raised on any Flink admin operation failure."""


class FlinkAdminUnavailableError(FlinkAdminError):
    """Raised when the underlying SDK or REST API is unreachable."""


@dataclass(frozen=True)
class FlinkJobOverview:
    jid: str
    name: str
    state: str
    start_time: int | None = None
    end_time: int | None = None
    duration: int | None = None
    tasks: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "jid": self.jid,
            "name": self.name,
            "state": self.state,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "tasks": dict(self.tasks or {}),
        }


@dataclass(frozen=True)
class FlinkSessionJob:
    name: str
    namespace: str
    state: str | None
    parallelism: int | None
    job_id: str | None
    jar_uri: str | None
    entry_class: str | None
    args: list[str]
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "state": self.state,
            "parallelism": self.parallelism,
            "job_id": self.job_id,
            "jar_uri": self.jar_uri,
            "entry_class": self.entry_class,
            "args": list(self.args),
            "raw": dict(self.raw or {}),
        }


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------
class FlinkRestClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 10.0,
    ) -> None:
        self._base = (base_url or getattr(settings, "flink_rest_url", "") or "").rstrip("/")
        self._timeout = float(timeout_s)

    @property
    def configured(self) -> bool:
        return bool(self._base)

    def _client(self):
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise FlinkAdminUnavailableError("httpx not installed") from exc
        return httpx.Client(timeout=self._timeout)

    def jobs_overview(self) -> list[FlinkJobOverview]:
        if not self.configured:
            raise FlinkAdminUnavailableError("flink_rest_url not configured")
        with self._client() as client:
            try:
                r = client.get(f"{self._base}/jobs/overview")
            except Exception as exc:  # noqa: BLE001
                raise FlinkAdminError(f"flink REST unreachable: {exc}") from exc
            if r.status_code >= 400:
                raise FlinkAdminError(f"jobs_overview {r.status_code}: {r.text}")
            data = r.json()
            jobs: list[FlinkJobOverview] = []
            for entry in data.get("jobs", []) or []:
                jobs.append(
                    FlinkJobOverview(
                        jid=str(entry.get("jid")),
                        name=str(entry.get("name")),
                        state=str(entry.get("state")),
                        start_time=entry.get("start-time"),
                        end_time=entry.get("end-time"),
                        duration=entry.get("duration"),
                        tasks=entry.get("tasks"),
                    )
                )
            return jobs

    def job_detail(self, job_id: str) -> dict[str, Any]:
        if not self.configured:
            raise FlinkAdminUnavailableError("flink_rest_url not configured")
        with self._client() as client:
            r = client.get(f"{self._base}/jobs/{job_id}")
            if r.status_code == 404:
                raise FlinkAdminError(f"job {job_id} not found")
            if r.status_code >= 400:
                raise FlinkAdminError(f"job_detail {r.status_code}: {r.text}")
            return r.json()

    def job_exceptions(self, job_id: str) -> dict[str, Any]:
        if not self.configured:
            raise FlinkAdminUnavailableError("flink_rest_url not configured")
        with self._client() as client:
            r = client.get(f"{self._base}/jobs/{job_id}/exceptions")
            if r.status_code >= 400:
                raise FlinkAdminError(f"exceptions {r.status_code}: {r.text}")
            return r.json()

    def trigger_savepoint(
        self,
        job_id: str,
        *,
        target_directory: str | None = None,
        cancel_job: bool = False,
    ) -> dict[str, Any]:
        if not self.configured:
            raise FlinkAdminUnavailableError("flink_rest_url not configured")
        body: dict[str, Any] = {"cancel-job": bool(cancel_job)}
        if target_directory:
            body["target-directory"] = target_directory
        with self._client() as client:
            r = client.post(f"{self._base}/jobs/{job_id}/savepoints", json=body)
            if r.status_code >= 400:
                raise FlinkAdminError(f"savepoint {r.status_code}: {r.text}")
            return r.json()


# ---------------------------------------------------------------------------
# Kubernetes session job wrapper
# ---------------------------------------------------------------------------
_K8S_LOCK = threading.Lock()
_K8S_CLIENT: Any = None


def _get_k8s_client() -> Any:
    global _K8S_CLIENT
    with _K8S_LOCK:
        if _K8S_CLIENT is not None:
            return _K8S_CLIENT
        try:
            from kubernetes import client as k_client, config as k_config  # type: ignore[import]
        except Exception as exc:  # pragma: no cover
            raise FlinkAdminUnavailableError("kubernetes SDK not installed") from exc
        try:
            try:
                k_config.load_incluster_config()
            except Exception:
                k_config.load_kube_config()
        except Exception as exc:  # noqa: BLE001
            raise FlinkAdminUnavailableError(f"kube config load failed: {exc}") from exc
        _K8S_CLIENT = k_client
        return _K8S_CLIENT


class FlinkSessionJobK8s:
    GROUP = "flink.apache.org"
    VERSION = "v1beta1"
    PLURAL = "flinksessionjobs"

    def __init__(self, *, namespace: str | None = None) -> None:
        self._namespace = namespace or getattr(settings, "flink_namespace", None) or "default"

    def _api(self):
        client = _get_k8s_client()
        return client.CustomObjectsApi()

    @staticmethod
    def _summarise(obj: dict[str, Any]) -> FlinkSessionJob:
        spec = obj.get("spec", {}) or {}
        job = spec.get("job", {}) or {}
        status = obj.get("status", {}) or {}
        job_status = status.get("jobStatus", {}) or {}
        return FlinkSessionJob(
            name=str((obj.get("metadata") or {}).get("name") or ""),
            namespace=str((obj.get("metadata") or {}).get("namespace") or ""),
            state=str(job.get("state") or job_status.get("state") or ""),
            parallelism=int(job.get("parallelism")) if job.get("parallelism") is not None else None,
            job_id=str(job_status.get("jobId")) if job_status.get("jobId") else None,
            jar_uri=str(job.get("jarURI")) if job.get("jarURI") else None,
            entry_class=str(job.get("entryClass")) if job.get("entryClass") else None,
            args=[str(a) for a in (job.get("args") or [])],
            raw=obj,
        )

    def list(self, *, namespace: str | None = None) -> list[FlinkSessionJob]:
        api = self._api()
        ns = namespace or self._namespace
        try:
            data = api.list_namespaced_custom_object(
                group=self.GROUP,
                version=self.VERSION,
                namespace=ns,
                plural=self.PLURAL,
            )
        except Exception as exc:  # noqa: BLE001
            raise FlinkAdminError(f"list_session_jobs failed: {exc}") from exc
        return [self._summarise(item) for item in data.get("items", [])]

    def get(self, name: str, *, namespace: str | None = None) -> FlinkSessionJob:
        api = self._api()
        ns = namespace or self._namespace
        try:
            obj = api.get_namespaced_custom_object(
                group=self.GROUP,
                version=self.VERSION,
                namespace=ns,
                plural=self.PLURAL,
                name=name,
            )
        except Exception as exc:  # noqa: BLE001
            raise FlinkAdminError(f"get_session_job {name} failed: {exc}") from exc
        return self._summarise(obj)

    def create(self, body: dict[str, Any]) -> FlinkSessionJob:
        api = self._api()
        ns = (body.get("metadata") or {}).get("namespace") or self._namespace
        try:
            obj = api.create_namespaced_custom_object(
                group=self.GROUP,
                version=self.VERSION,
                namespace=ns,
                plural=self.PLURAL,
                body=body,
            )
        except Exception as exc:  # noqa: BLE001
            raise FlinkAdminError(f"create_session_job failed: {exc}") from exc
        return self._summarise(obj)

    def patch(
        self, name: str, patch: dict[str, Any], *, namespace: str | None = None
    ) -> FlinkSessionJob:
        api = self._api()
        ns = namespace or self._namespace
        try:
            obj = api.patch_namespaced_custom_object(
                group=self.GROUP,
                version=self.VERSION,
                namespace=ns,
                plural=self.PLURAL,
                name=name,
                body=patch,
            )
        except Exception as exc:  # noqa: BLE001
            raise FlinkAdminError(f"patch_session_job {name} failed: {exc}") from exc
        return self._summarise(obj)

    def delete(self, name: str, *, namespace: str | None = None) -> None:
        api = self._api()
        ns = namespace or self._namespace
        try:
            api.delete_namespaced_custom_object(
                group=self.GROUP,
                version=self.VERSION,
                namespace=ns,
                plural=self.PLURAL,
                name=name,
            )
        except Exception as exc:  # noqa: BLE001
            raise FlinkAdminError(f"delete_session_job {name} failed: {exc}") from exc

    def set_state(self, name: str, state: str, *, namespace: str | None = None) -> FlinkSessionJob:
        if state not in {"running", "suspended"}:
            raise FlinkAdminError(f"invalid state {state!r} (running|suspended)")
        return self.patch(name, {"spec": {"job": {"state": state}}}, namespace=namespace)

    def scale(
        self, name: str, parallelism: int, *, namespace: str | None = None
    ) -> FlinkSessionJob:
        return self.patch(
            name,
            {"spec": {"job": {"parallelism": int(parallelism)}}},
            namespace=namespace,
        )


_REST_SINGLETON: FlinkRestClient | None = None
_K8S_SINGLETON: FlinkSessionJobK8s | None = None
_SINGLETON_LOCK = threading.Lock()


def get_flink_rest_client() -> FlinkRestClient:
    global _REST_SINGLETON
    with _SINGLETON_LOCK:
        if _REST_SINGLETON is None:
            _REST_SINGLETON = FlinkRestClient()
        return _REST_SINGLETON


def get_flink_session_jobs() -> FlinkSessionJobK8s:
    global _K8S_SINGLETON
    with _SINGLETON_LOCK:
        if _K8S_SINGLETON is None:
            _K8S_SINGLETON = FlinkSessionJobK8s()
        return _K8S_SINGLETON


__all__ = [
    "FlinkAdminError",
    "FlinkAdminUnavailableError",
    "FlinkJobOverview",
    "FlinkRestClient",
    "FlinkSessionJob",
    "FlinkSessionJobK8s",
    "get_flink_rest_client",
    "get_flink_session_jobs",
]
