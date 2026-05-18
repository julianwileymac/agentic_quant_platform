"""GCP GKE :class:`KubernetesAdapter` — auth via google-auth + GKE Container API.

Subclasses :class:`InClusterAdapter` so the pod-level surface is
inherited unchanged. Only :meth:`_load_config` is overridden:

- Uses :func:`google.auth.default` to pick up Application Default
  Credentials (operator laptop: gcloud user creds; CI: service
  account file; in-cluster: Workload Identity).
- Calls :class:`google.cloud.container_v1.ClusterManagerClient` to
  fetch the cluster's endpoint + CA certificate.
- Refreshes the OAuth token via the credentials object and assembles
  a Configuration object pointing at the GKE control plane.

GCP SDK is optional: missing imports degrade :meth:`is_available` to
``False`` so routes return 503 rather than crash.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from aqp.kubernetes.adapters.in_cluster import InClusterAdapter

logger = logging.getLogger(__name__)


class GcpGkeAdapter(InClusterAdapter):
    """GCP GKE adapter built on the standard kubernetes-python-client."""

    adapter_kind = "gcp_gke"
    adapter_alias = "GcpGkeAdapter"

    def __init__(self) -> None:
        self._loaded = False
        self._k8s_module = None
        self._cluster_name: str | None = None
        self._project_id: str | None = None
        self._region: str | None = None
        try:
            self._load_config()
        except Exception as exc:  # noqa: BLE001
            logger.debug("GcpGkeAdapter unavailable: %s", exc)

    def _load_config(self) -> None:  # type: ignore[override]
        try:
            import kubernetes as k8s  # type: ignore
        except ImportError:
            self._loaded = False
            return
        try:
            import google.auth  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
            from google.cloud import container_v1  # type: ignore
        except ImportError:
            logger.info(
                "GcpGkeAdapter requires google-cloud-container + google-auth; "
                "install with 'pip install agentic-quant-platform[cloud-gcp]'"
            )
            self._loaded = False
            return

        try:
            from aqp.config import settings

            cluster_name = (str(getattr(settings, "gcp_gke_cluster_name", "") or "")).strip()
            project_id = (str(getattr(settings, "gcp_project_id", "") or "")).strip()
            region = (str(getattr(settings, "gcp_region", "") or "")).strip()
        except Exception:
            cluster_name = project_id = region = ""

        if not cluster_name or not project_id or not region:
            logger.info(
                "GcpGkeAdapter: AQP_GCP_GKE_CLUSTER_NAME / AQP_GCP_PROJECT_ID / "
                "AQP_GCP_REGION not all set; disabled"
            )
            self._loaded = False
            return

        try:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials.refresh(Request())
            client = container_v1.ClusterManagerClient(credentials=credentials)
            cluster_path = f"projects/{project_id}/locations/{region}/clusters/{cluster_name}"
            cluster = client.get_cluster(name=cluster_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GcpGkeAdapter cluster lookup failed: %s", exc)
            self._loaded = False
            return

        try:
            ca_bytes = base64.b64decode(cluster.master_auth.cluster_ca_certificate)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GcpGkeAdapter CA decode failed: %s", exc)
            self._loaded = False
            return

        import tempfile

        ca_file = tempfile.NamedTemporaryFile(
            mode="wb", suffix="-gke-ca.pem", delete=False
        )
        try:
            ca_file.write(ca_bytes)
            ca_file.flush()
        finally:
            ca_file.close()

        configuration = k8s.client.Configuration()
        configuration.host = f"https://{cluster.endpoint}"
        configuration.ssl_ca_cert = ca_file.name
        configuration.api_key = {"authorization": f"Bearer {credentials.token}"}
        k8s.client.Configuration.set_default(configuration)

        self._loaded = True
        self._k8s_module = k8s
        self._cluster_name = cluster_name
        self._project_id = project_id
        self._region = region
        logger.info(
            "GcpGkeAdapter loaded cluster=%s project=%s region=%s",
            cluster_name,
            project_id,
            region,
        )

    def describe(self) -> dict[str, Any]:
        out = super().describe()
        out.update(
            {
                "cluster_name": self._cluster_name,
                "project_id": self._project_id,
                "region": self._region,
            }
        )
        return out


__all__ = ["GcpGkeAdapter"]
