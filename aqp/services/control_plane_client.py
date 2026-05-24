"""HTTP client for the AQP control plane (``aqp_control_plane``).

Phase 3 of the AQP infra-expansion plan. Replaces
:class:`aqp.services.cluster_mgmt_client.ClusterMgmtClient` (which
talks to the deprecated ``rpi-k8s-management`` API) with a typed
client targeting the new ``/manage/*`` route groups:

- ``/manage/topology`` (Phase 0)
- ``/manage/streaming/*`` (Phase 3)
- ``/manage/observability/*`` (Phase 3)
- ``/manage/lakehouse/*`` (Phase 3)
- ``/manage/timeseries/*`` (Phase 3)
- ``/manage/data-plane/*`` (Phase 3)
- ``/manage/workloads/halt`` (kill-switch fan-out)

Resolution order (matching the topology fallback in Phase 0):

1. ``base_url`` ctor arg.
2. ``settings.cluster_mgmt_url`` env override (``AQP_CLUSTER_MGMT_URL``).
3. Topology service: ``services > aqp-cp > endpoints.manage``.
4. ``http://aqp-cp.aqp-admin.svc.cluster.local:9000`` (in-cluster
   default).

Authentication: M2M JWT issued by Auth0 (audience matches
``settings.auth0_mgmt_api_audience``). The token resolver lives in
:mod:`aqp.auth.m2m`. Tests can pass ``token=...`` directly to skip
the resolver.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


class ControlPlaneError(RuntimeError):
    """Raised when the control plane responds with an error."""


def _resolve_base_url() -> str:
    """Resolve the control-plane base URL using the documented precedence."""
    explicit = getattr(settings, "cluster_mgmt_url", "") or ""
    if explicit and "/manage" not in explicit:
        # Operator pointed cluster_mgmt_url at the LEGACY rpi backend.
        # The legacy ClusterMgmtClient is the right caller for that
        # path; this client refuses to use it.
        if getattr(settings, "control_plane_legacy_fallback", True):
            return ""
    if explicit:
        return explicit.rstrip("/")
    # Fall back to the topology snapshot for the aqp-cp service.
    try:
        from aqp.deployment.topology import get_deployment_topology

        topology = get_deployment_topology()
        cp_service = topology.service_map.get("aqp-cp")
        if cp_service and cp_service.endpoints:
            url = cp_service.primary_url() or cp_service.endpoints.get("manage")
            if url:
                return url.rstrip("/")
    except Exception:  # noqa: BLE001
        logger.debug("topology fallback for aqp-cp endpoint failed", exc_info=True)
    return "http://aqp-cp.aqp-admin.svc.cluster.local:9000"


class AQPControlPlaneClient:
    """Typed client for ``aqp_control_plane``'s ``/manage/*`` routes."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._base = (base_url or _resolve_base_url()).rstrip("/")
        self._token = token or self._mint_m2m_token()
        self._timeout = float(timeout_s)

    @staticmethod
    def _mint_m2m_token() -> str:
        """Mint an M2M JWT for the control plane via :class:`M2MTokenIssuer`.

        Returns an empty string when the issuer cannot mint (no audience
        configured, no IdP, or token request rejected). Callers running
        in the unauthenticated local-dev mode (``auth_required=False``)
        get an empty bearer; the control-plane settings respect that
        when ``auth_required`` is False on the receiving side.
        """
        try:
            from aqp.auth.m2m import M2MTokenIssuer

            audience = (
                getattr(settings, "auth_m2m_audience", "")
                or getattr(settings, "auth_oidc_audience", "")
                or "https://api.aqp.internal/manage"
            )
            issuer = M2MTokenIssuer()
            result = issuer.token_for(
                "aqp_control_plane",
                purpose="default",
                audience=audience,
            )
            if result is None:
                return ""
            return str(result.access_token or "")
        except Exception:  # noqa: BLE001
            logger.debug("M2M token mint failed; using empty bearer", exc_info=True)
            return ""

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def configured(self) -> bool:
        return bool(self._base)

    def _client(self) -> httpx.Client:
        headers: dict[str, str] = {
            "User-Agent": "aqp-control-plane-client",
            "Accept": "application/json",
        }
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
            raise ControlPlaneError("aqp_control_plane URL not configured")
        url = f"{self._base}{path}"
        with self._client() as client:
            try:
                response = client.request(method, url, params=params, json=json_body)
            except Exception as exc:  # noqa: BLE001
                raise ControlPlaneError(
                    f"control plane unreachable: {exc}"
                ) from exc
            if response.status_code == 204:
                return None
            if response.status_code >= 400:
                detail = response.text or response.reason_phrase
                raise ControlPlaneError(
                    f"{method} {url}: {response.status_code} {detail}"
                )
            try:
                return response.json()
            except ValueError:
                return response.text

    # ------------------------------------------------------------------ topology
    def topology_snapshot(self, *, include_targets: bool = True) -> dict[str, Any]:
        return self._request(
            "GET",
            "/manage/topology",
            params={"include_targets": str(include_targets).lower()},
        )

    def describe_service(self, service_id: str) -> dict[str, Any]:
        return self._request("GET", f"/manage/topology/services/{service_id}")

    def resolve_endpoint(self, service_id: str, name: str = "") -> dict[str, Any]:
        return self._request(
            "GET",
            f"/manage/topology/services/{service_id}/endpoint",
            params={"name": name} if name else None,
        )

    # ------------------------------------------------------------------ streaming
    def list_streaming_clusters(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/manage/streaming/clusters")
        return payload.get("data", []) if isinstance(payload, dict) else []

    def streaming_cluster_health(self, cluster_id: str) -> dict[str, Any]:
        return self._request("GET", f"/manage/streaming/clusters/{cluster_id}/health")

    # ------------------------------------------------------------------ observability
    def prometheus_query(self, expr: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/manage/observability/prometheus/query",
            params={"query": expr},
        )

    def list_grafana_dashboards(self) -> dict[str, Any]:
        return self._request("GET", "/manage/observability/grafana/dashboards")

    def list_phoenix_projects(self) -> dict[str, Any]:
        return self._request("GET", "/manage/observability/phoenix/projects")

    # ------------------------------------------------------------------ lakehouse
    def list_lakehouse_clusters(self) -> dict[str, Any]:
        return self._request("GET", "/manage/lakehouse/clusters")

    def list_iceberg_namespaces(self) -> dict[str, Any]:
        return self._request("GET", "/manage/lakehouse/iceberg/namespaces")

    def list_hudi_tables(self) -> dict[str, Any]:
        return self._request("GET", "/manage/lakehouse/hudi/tables")

    # ------------------------------------------------------------------ timeseries
    def questdb_status(self) -> dict[str, Any]:
        return self._request("GET", "/manage/timeseries/questdb/status")

    def questdb_tables(self) -> dict[str, Any]:
        return self._request("GET", "/manage/timeseries/questdb/tables")

    # ------------------------------------------------------------------ workloads
    def halt_workloads(self, *, reason: str = "kill-switch") -> dict[str, Any]:
        return self._request(
            "POST",
            "/manage/workloads/halt",
            json_body={"reason": reason},
        )

    def halt_streaming(self) -> dict[str, Any]:
        return self._request("POST", "/manage/streaming/halt")

    def halt_lakehouse(self) -> dict[str, Any]:
        return self._request("POST", "/manage/lakehouse/halt")


_singleton: AQPControlPlaneClient | None = None


def get_control_plane_client() -> AQPControlPlaneClient:
    """Return the cached process-wide control-plane client."""
    global _singleton
    if _singleton is None:
        _singleton = AQPControlPlaneClient()
    return _singleton


def reset_control_plane_client() -> None:
    """Test helper - drop the cached singleton."""
    global _singleton
    _singleton = None


__all__ = [
    "AQPControlPlaneClient",
    "ControlPlaneError",
    "get_control_plane_client",
    "reset_control_plane_client",
]
