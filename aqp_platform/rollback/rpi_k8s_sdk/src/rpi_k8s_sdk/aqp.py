"""Convenience wrappers for using the rpi_kubernetes platform from AQP code.

The Agentic Quant Platform (`agentic_quant_platform`) runs locally on a
developer laptop most of the time, but its production data plane lives in
this Kubernetes cluster.  The helpers in this module let an AQP user start
a session, hand off a backtest to the in-cluster Argo runners, and register
a trained model with MLflow + KServe in one or two lines:

    from rpi_k8s_sdk.aqp import aqp_session, register_model

    with aqp_session():
        register_model("mlflow-run-id-here", strategy_name="momentum-50d")

The session context configures tracing, brings up the necessary tunnels,
and exports the right env vars so AQP's own clients (MLflow, MinIO,
Iceberg) can reach the cluster.

Phase 7 (refactor) extension
----------------------------

The new :class:`AqpControlPlaneClient` is the canonical typed client to
``aqp_control_plane`` — the isolated AQP control-plane micro-project
introduced by the refactor (ADR 005). It speaks the
``/manage/*`` REST surface (deployments / config / telemetry / health)
and forwards an Auth0 bearer token when one is configured.

The existing :func:`aqp_session`, :func:`submit_backtest`, and
:func:`register_model` helpers remain as thin wrappers around the
in-cluster platform services (MLflow / Argo / KServe). New code that
wants to manage AQP workloads should reach for
:class:`AqpControlPlaneClient` instead of the deprecated
``management/backend`` HTTP API in this repo.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
from typing import Any, Iterator

import httpx

from .access import LocalAccessSettings, load_settings
from .mlflow import MLflowClient
from .pipelines import ArgoPipelineClient, PipelineRun
from .serving import ModelStore, kserve_inferenceservice_manifest
from .tracing import configure_tracing
from .tunnels import LocalTunnelManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AqpControlPlaneClient — Phase 7 addition
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class AqpControlPlaneSettings:
    """Connection settings for ``aqp_control_plane`` HTTP API.

    The defaults match the docker-compose stack
    (``http://localhost:9000``); override via env vars in production.
    """

    base_url: str = "http://localhost:9000"
    bearer_token: str = ""
    timeout_seconds: float = 30.0
    request_id_prefix: str = "rpi-k8s-sdk"

    @classmethod
    def from_env(cls) -> AqpControlPlaneSettings:
        return cls(
            base_url=os.environ.get(
                "AQP_CONTROL_PLANE_URL", "http://localhost:9000"
            ).rstrip("/"),
            bearer_token=os.environ.get("AQP_CONTROL_PLANE_TOKEN", ""),
            timeout_seconds=float(
                os.environ.get("AQP_CONTROL_PLANE_TIMEOUT_SECONDS", "30")
            ),
        )


class AqpControlPlaneClient:
    """Typed HTTP client for the AQP control plane (``/manage/*``).

    Usage::

        from rpi_k8s_sdk.aqp import AqpControlPlaneClient

        with AqpControlPlaneClient.from_env() as client:
            status = client.list_deployments()
            client.scale_deployment("aqp-worker", 4)

    Every mutating call returns the ``ResponseEnvelope`` shape
    (``{"status": "ok", "data": ..., "error": null}``) emitted by the
    control plane. The client auto-attaches the bearer token (when
    configured) and a per-request ``X-Request-Id``.
    """

    def __init__(self, settings: AqpControlPlaneSettings | None = None) -> None:
        self.settings = settings or AqpControlPlaneSettings.from_env()
        self._http = httpx.Client(
            base_url=self.settings.base_url,
            timeout=self.settings.timeout_seconds,
            headers=self._default_headers(),
        )

    def _default_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.settings.bearer_token:
            headers["Authorization"] = f"Bearer {self.settings.bearer_token}"
        return headers

    def _request_id(self) -> str:
        import secrets

        return f"{self.settings.request_id_prefix}-{secrets.token_hex(8)}"

    def _envelope(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {"detail": response.text}
            raise AqpControlPlaneError(
                f"AQP control plane returned {response.status_code}",
                status_code=response.status_code,
                body=body,
            )
        return response.json()

    # ---- health -----------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return ``/manage/health`` payload (unauthenticated endpoint)."""
        return self._envelope(self._http.get("/manage/health"))

    # ---- deployments -----------------------------------------------

    def list_deployments(self, *, namespace: str | None = None) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._envelope(self._http.get("/manage/deployments", params=params))

    def get_deployment(
        self, service_id: str, *, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._envelope(
            self._http.get(f"/manage/deployments/{service_id}", params=params)
        )

    def start_deployment(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Start/update a deployment.

        ``spec`` must follow the ``DeploymentSpec`` shape — at minimum
        ``service_id`` + ``image``. Reference:
        :class:`aqp_platform_core.models.DeploymentSpec`.
        """
        service_id = spec.get("service_id")
        if not service_id:
            raise ValueError("spec missing 'service_id'")
        return self._envelope(
            self._http.post(
                f"/manage/deployments/{service_id}/start",
                json=spec,
                headers={"X-Request-Id": self._request_id()},
            )
        )

    def stop_deployment(
        self, service_id: str, *, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._envelope(
            self._http.post(
                f"/manage/deployments/{service_id}/stop",
                params=params,
                headers={"X-Request-Id": self._request_id()},
            )
        )

    def scale_deployment(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"replicas": int(replicas)}
        if namespace:
            params["namespace"] = namespace
        return self._envelope(
            self._http.patch(
                f"/manage/deployments/{service_id}/scale",
                params=params,
                headers={"X-Request-Id": self._request_id()},
            )
        )

    def restart_deployment(
        self, service_id: str, *, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._envelope(
            self._http.post(
                f"/manage/deployments/{service_id}/restart",
                params=params,
                headers={"X-Request-Id": self._request_id()},
            )
        )

    def exec_deployment(
        self,
        service_id: str,
        command: list[str],
        *,
        namespace: str | None = None,
        container: str | None = None,
        timeout_seconds: int = 60,
        stdin_b64: str | None = None,
    ) -> dict[str, Any]:
        return self._envelope(
            self._http.post(
                f"/manage/deployments/{service_id}/exec",
                json={
                    "command": command,
                    "namespace": namespace,
                    "container": container,
                    "timeout_seconds": timeout_seconds,
                    "stdin_b64": stdin_b64,
                },
                headers={"X-Request-Id": self._request_id()},
            )
        )

    def deployment_logs(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        container: str | None = None,
        tail: int = 200,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"tail": int(tail)}
        if namespace:
            params["namespace"] = namespace
        if container:
            params["container"] = container
        return self._envelope(
            self._http.get(f"/manage/deployments/{service_id}/logs", params=params)
        )

    def delete_deployment(
        self, service_id: str, *, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._envelope(
            self._http.delete(
                f"/manage/deployments/{service_id}",
                params=params,
                headers={"X-Request-Id": self._request_id()},
            )
        )

    # ---- config / telemetry ----------------------------------------

    def get_config(
        self, service_id: str, *, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        return self._envelope(
            self._http.get(f"/manage/config/{service_id}", params=params)
        )

    def patch_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        service_id = patch.get("service_id")
        if not service_id:
            raise ValueError("patch missing 'service_id'")
        return self._envelope(
            self._http.patch(
                f"/manage/config/{service_id}",
                json=patch,
                headers={"X-Request-Id": self._request_id()},
            )
        )

    def telemetry_snapshot(self) -> dict[str, Any]:
        return self._envelope(self._http.get("/manage/telemetry/snapshot"))

    # ---- lifecycle --------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AqpControlPlaneClient:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    @classmethod
    def from_env(cls) -> AqpControlPlaneClient:
        return cls(AqpControlPlaneSettings.from_env())


class AqpControlPlaneError(RuntimeError):
    """Raised when the AQP control plane returns a 4xx/5xx response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@contextlib.contextmanager
def aqp_session(
    *,
    service_name: str = "aqp-local",
    settings: LocalAccessSettings | None = None,
    tunnels: bool | None = None,
) -> Iterator[LocalAccessSettings]:
    """Configure tracing + tunnels + env for an AQP local session.

    Parameters
    ----------
    service_name:
        Reported in OpenTelemetry spans (``service.name``).
    settings:
        Pre-built :class:`LocalAccessSettings`.  When ``None``, loads from
        environment via :func:`load_settings`.
    tunnels:
        Whether to start ``kubectl port-forward`` tunnels to the cluster
        (MLflow, OTel, Argo, DataHub).  When ``None``, follows
        ``settings.auto_tunnel``.
    """

    active = settings or load_settings()
    if tunnels is None:
        tunnels = active.auto_tunnel

    # Export the canonical env vars so AQP's own ``aqp.config.settings``
    # reads pick them up.
    for key, value in active.to_env().items():
        os.environ.setdefault(key, value)
    # Also export the AQP-namespaced aliases so any AQP_OTEL_* config
    # consumers keep working without explicit overrides.
    os.environ.setdefault("AQP_OTEL_ENDPOINT", active.otlp_endpoint)
    os.environ.setdefault("AQP_OTEL_SERVICE_NAME", service_name)

    configure_tracing(
        service_name=service_name,
        endpoint=active.otlp_endpoint,
        namespace="aqp",
        instrument_kafka=False,
        instrument_httpx=True,
    )

    if not tunnels:
        yield active
        return

    manager = LocalTunnelManager(active)
    services = [active.datahub_gms, active.otel_collector, active.argo_server]
    with manager.started(*services):
        logger.info("AQP session tunnels online: %s", [s.name for s in services])
        yield active


def submit_backtest(
    *,
    template_name: str = "aqp-backtest",
    name: str = "aqp-run",
    parameters: dict[str, str] | None = None,
    namespace: str | None = None,
    settings: LocalAccessSettings | None = None,
) -> PipelineRun:
    """Submit an AQP backtest as an Argo Workflow.

    Thin wrapper around :class:`ArgoPipelineClient.submit_template` so AQP
    code does not have to import the lower-level pipeline API.
    """

    client = ArgoPipelineClient(settings=settings)
    return client.submit_template(
        template_name=template_name,
        name=name,
        parameters=parameters or {},
        namespace=namespace,
    )


def register_model(
    run_id: str,
    *,
    strategy_name: str,
    artifact_path: str = "model",
    runtime: str = "sklearn",
    deploy: bool = True,
    settings: LocalAccessSettings | None = None,
) -> dict[str, Any]:
    """Promote an MLflow run into a KServe-served model.

    Steps
    -----
    1. Pull the artifact directory from MLflow into the cluster's model bucket.
    2. Optionally apply a KServe ``InferenceService`` manifest pointing at the
       new ``s3://`` URI.

    Returns the artifact + manifest summary so callers can log it.
    """

    active = settings or load_settings()
    store = ModelStore(active)
    artifact = store.from_mlflow_run(run_id=run_id, artifact_path=artifact_path)
    manifest = kserve_inferenceservice_manifest(
        name=strategy_name,
        model_uri=artifact.s3_uri,
        runtime=runtime,
    )
    summary: dict[str, Any] = {
        "artifact": {
            "model_id": artifact.model_id,
            "bucket": artifact.bucket,
            "prefix": artifact.prefix,
            "s3_uri": artifact.s3_uri,
        },
        "manifest": manifest,
    }
    if deploy:
        applied = store.deploy_to_kserve(manifest)
        summary["status"] = applied.get("status")
        summary["deployed"] = True
    else:
        summary["deployed"] = False
    return summary


def latest_mlflow_run(experiment_name: str, *, settings: LocalAccessSettings | None = None) -> str | None:
    """Return the most recent MLflow run ID under ``experiment_name``."""

    client = MLflowClient(settings or load_settings())
    runs = client.list_runs(experiment_name=experiment_name, max_results=1)
    if not runs:
        return None
    return runs[0].run_id


__all__ = [
    "AqpControlPlaneClient",
    "AqpControlPlaneError",
    "AqpControlPlaneSettings",
    "aqp_session",
    "latest_mlflow_run",
    "register_model",
    "submit_backtest",
]
