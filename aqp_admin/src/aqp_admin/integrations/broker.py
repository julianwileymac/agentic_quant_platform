"""HTTP brokers for the admin BFF.

Every outbound call attaches a Bearer token minted via the
platform-core M2M broker (Entra-primary). Failure modes are
normalised to :class:`AdminBrokerError` with a typed ``code`` so
route handlers can wrap them in :class:`ResponseEnvelope.error`
without sniffing string content.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

import httpx

from aqp_platform_core.auth.m2m import (
    M2MBrokerError,
    M2MTokenBroker,
    M2MTokenBrokerConfig,
)
from aqp_platform_core.auth.providers.msal_entra import MsalEntraValidator
from aqp_platform_core.credentials.protocol import (
    Credential,
    CredentialKey,
    PRIORITY_ENV,
    SecretStore,
)

from aqp_admin.settings import AdminSettings, get_settings

logger = logging.getLogger(__name__)


class AdminBrokerError(RuntimeError):
    """Normalised broker-side failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "broker_error",
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


# ---------------------------------------------------------------------------
# CredentialResolver-compatible env store
# ---------------------------------------------------------------------------


class EnvSecretStore(SecretStore):
    """Minimal env-var store used by the admin M2M broker.

    Looks for ``AQP_ADMIN_M2M_<SERVICE>_<PURPOSE>_<FIELD>`` env vars.
    For example, with ``service='aqp-admin-to-cp'`` /
    ``purpose='client_credentials'``:

    - ``AQP_ADMIN_M2M_AQP_ADMIN_TO_CP_CLIENT_CREDENTIALS_CLIENT_ID``
    - ``AQP_ADMIN_M2M_AQP_ADMIN_TO_CP_CLIENT_CREDENTIALS_CLIENT_SECRET``

    Hyphens normalise to underscores so the service/purpose names
    used elsewhere in the codebase remain ergonomic.
    """

    store_kind = "admin_env"
    store_priority = PRIORITY_ENV

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = dict(env if env is not None else os.environ)

    def get(self, key: CredentialKey) -> Credential | None:
        prefix = self._key_prefix(key)
        client_id = self._env.get(f"{prefix}_CLIENT_ID")
        client_secret = self._env.get(f"{prefix}_CLIENT_SECRET")
        if not client_id and not client_secret:
            return None
        fields: dict[str, str] = {}
        if client_id:
            fields["client_id"] = client_id
        if client_secret:
            fields["client_secret"] = client_secret
        return Credential(fields=fields, source=self.store_kind)

    @staticmethod
    def _key_prefix(key: CredentialKey) -> str:
        service = key.service.replace("-", "_").upper()
        purpose = key.purpose.replace("-", "_").upper()
        return f"AQP_ADMIN_M2M_{service}_{purpose}"


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _BrokerHttpClient:
    """Bundles a long-lived httpx client + audience for one upstream."""

    base_url: str
    audience: str
    timeout_seconds: float = 10.0
    _client: httpx.AsyncClient | None = None

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class _BaseBroker:
    """Common HTTP plumbing — bearer header + error normalisation."""

    def __init__(
        self,
        *,
        m2m: M2MTokenBroker,
        http: _BrokerHttpClient,
        scopes: tuple[str, ...] = (),
    ) -> None:
        self._m2m = m2m
        self._http = http
        self._scopes = scopes

    @property
    def base_url(self) -> str:
        return self._http.base_url

    async def close(self) -> None:
        await self._http.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        bearer_passthrough: str | None = None,
    ) -> httpx.Response:
        client = await self._http.client()
        if bearer_passthrough:
            bearer = bearer_passthrough
        else:
            try:
                grant = await self._m2m.acquire(
                    audience=self._http.audience,
                    scopes=self._scopes,
                )
                bearer = grant.access_token
            except M2MBrokerError as exc:
                # In local dev / sandbox we may not have an Entra app
                # registration handy. Log + continue without the
                # header so the upstream (which itself may have auth
                # disabled) can still respond.
                if get_settings().auth_enabled:
                    raise AdminBrokerError(
                        "admin broker bearer mint failed",
                        code="m2m_bearer_mint_failed",
                    ) from exc
                logger.warning(
                    "admin broker bearer mint failed; sending unauthenticated in local mode"
                )
                bearer = ""
        headers: dict[str, str] = {}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            response = await client.request(
                method.upper(),
                path,
                json=json_body,
                params=params,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise AdminBrokerError(
                f"upstream {self._http.base_url}{path} unreachable: {exc}",
                code="upstream_unreachable",
            ) from exc
        if response.status_code >= 500:
            raise AdminBrokerError(
                f"upstream {self._http.base_url}{path} returned 5xx",
                code="upstream_5xx",
                status_code=response.status_code,
                details={"body": response.text[:1024]},
            )
        return response


class ControlPlaneBroker(_BaseBroker):
    """Calls ``/manage/*`` on the AQP control plane."""

    async def list_deployments(self, namespace: str | None = None) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request("GET", "/manage/deployments", params=params)
        return response.json()

    async def get_deployment(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request(
            "GET",
            f"/manage/deployments/{service_id}",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def start_deployment(
        self,
        service_id: str,
        spec: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/manage/deployments/{service_id}/start",
            json_body=spec,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def stop_deployment(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request(
            "POST",
            f"/manage/deployments/{service_id}/stop",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def scale_deployment(
        self,
        service_id: str,
        *,
        replicas: int,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"replicas": replicas}
        if namespace:
            params["namespace"] = namespace
        response = await self._request(
            "PATCH",
            f"/manage/deployments/{service_id}/scale",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def restart_deployment(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request(
            "POST",
            f"/manage/deployments/{service_id}/restart",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def exec_deployment(
        self,
        service_id: str,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/manage/deployments/{service_id}/exec",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def deployment_logs(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        container: str | None = None,
        tail: int = 200,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"tail": tail}
        if namespace:
            params["namespace"] = namespace
        if container:
            params["container"] = container
        response = await self._request(
            "GET",
            f"/manage/deployments/{service_id}/logs",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def delete_deployment(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request(
            "DELETE",
            f"/manage/deployments/{service_id}",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_config(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request(
            "GET",
            f"/manage/config/{service_id}",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def patch_config(
        self,
        service_id: str,
        body: dict[str, Any],
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request(
            "PATCH",
            f"/manage/config/{service_id}",
            json_body=body,
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def telemetry_snapshot(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/manage/telemetry/snapshot",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def provision_tenant(
        self,
        tenant_id: str,
        spec: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/manage/tenants/{tenant_id}/provision",
            json_body=spec,
        )
        return response.json()

    async def render_tenant_bundle(
        self,
        tenant_id: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/manage/tenants/{tenant_id}/render",
            json_body=spec,
        )
        return response.json()

    async def tenant_status(self, tenant_id: str) -> dict[str, Any]:
        response = await self._request("GET", f"/manage/tenants/{tenant_id}")
        return response.json()

    async def halt_workloads(self, reason: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/manage/workloads/halt",
            json_body={"reason": reason},
        )
        return response.json()

    async def workloads_halt_status(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/manage/workloads/halt/status",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def halt_terraform(self, reason: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/manage/terraform/halt",
            json_body={"reason": reason},
        )
        return response.json()

    async def terraform_run(
        self,
        workspace_id: str,
        action: str,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/manage/terraform/workspaces/{workspace_id}/{action}",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def terraform_halt_status(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/manage/terraform/halt/status",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def clear_terraform_halt(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "DELETE",
            "/manage/terraform/halt",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def submit_build(self, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("POST", "/manage/builds", json_body=body)
        return response.json()

    async def build_status(
        self, job_name: str, *, namespace: str | None = None
    ) -> dict[str, Any]:
        params = {"namespace": namespace} if namespace else None
        response = await self._request(
            "GET", f"/manage/builds/{job_name}", params=params
        )
        return response.json()

    async def prometheus_query_tenant(
        self,
        *,
        expression: str,
        time: float | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"query": expression}
        if time is not None:
            params["time"] = time
        response = await self._request(
            "POST",
            "/manage/observability/prometheus/query/tenant",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()


class MonolithBroker(_BaseBroker):
    """Calls the AQP monolith REST + DataMCP surfaces."""

    async def list_terraform_providers(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/terraform/providers",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def create_terraform_provider(
        self,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/terraform/providers",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_terraform_stacks(
        self,
        *,
        module_kind: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params = {"module_kind": module_kind} if module_kind else None
        response = await self._request(
            "GET",
            "/terraform/stacks",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_terraform_stack(
        self,
        stack_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/terraform/stacks/{stack_id}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_terraform_stack_versions(
        self,
        stack_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/terraform/stacks/{stack_id}/versions",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_terraform_stack_version(
        self,
        stack_id: str,
        version_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/terraform/stacks/{stack_id}/versions/{version_id}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_terraform_workspaces(
        self,
        *,
        environment: str | None = None,
        archived: bool = False,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"archived": archived}
        if environment:
            params["environment"] = environment
        response = await self._request(
            "GET",
            "/terraform/workspaces",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def create_terraform_workspace(
        self,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/terraform/workspaces",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_terraform_workspace(
        self,
        workspace_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/terraform/workspaces/{workspace_id}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def archive_terraform_workspace(
        self,
        workspace_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "DELETE",
            f"/terraform/workspaces/{workspace_id}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def terraform_state_outputs(
        self,
        workspace_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/terraform/workspaces/{workspace_id}/state/outputs",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def unlock_terraform_workspace(
        self,
        workspace_id: str,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/terraform/workspaces/{workspace_id}/unlock",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_terraform_runs(
        self,
        *,
        workspace_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if workspace_id:
            params["workspace_id"] = workspace_id
        if status_filter:
            params["status"] = status_filter
        response = await self._request(
            "GET",
            "/terraform/runs",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_terraform_run(
        self,
        run_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/terraform/runs/{run_id}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def cancel_terraform_run(
        self,
        run_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/terraform/runs/{run_id}/cancel",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def terraform_halt(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/terraform/halt",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def cluster_status(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/cluster/status",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_pods(
        self,
        namespace: str,
        *,
        label_selector: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {"label_selector": label_selector} if label_selector else None
        response = await self._request(
            "GET",
            f"/cluster/pods/{namespace}",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def exec_in_pod(
        self,
        namespace: str,
        name: str,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/cluster/pods/{namespace}/{name}/exec",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def put_pod_archive(
        self,
        namespace: str,
        name: str,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/cluster/pods/{namespace}/{name}/archive",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_pod_archive(
        self,
        namespace: str,
        name: str,
        *,
        path: str,
        container: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> httpx.Response:
        params: dict[str, Any] = {"path": path}
        if container:
            params["container"] = container
        return await self._request(
            "GET",
            f"/cluster/pods/{namespace}/{name}/archive",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )

    async def list_admin_audit_runs(
        self,
        *,
        limit: int = 100,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/_internal/audit/admin-runs",
            params={"limit": limit},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def cloudflare_health(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/cloudflare/health",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_organizations(
        self, *, bearer_passthrough: str | None = None
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.tenancy.list_organizations/invoke",
            json_body={},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_organization(
        self, org_id: str, *, bearer_passthrough: str | None = None
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.tenancy.get_organization/invoke",
            json_body={"org_id": org_id},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_invites(
        self, org_id: str | None = None, *, bearer_passthrough: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if org_id:
            body["org_id"] = org_id
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.tenancy.list_invites/invoke",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def create_invite(
        self,
        *,
        org_id: str,
        email: str,
        role: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/tenancy/invites",
            json_body={"org_id": org_id, "email": email, "role": role},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_entra_links(
        self, *, bearer_passthrough: str | None = None
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.tenancy.list_entra_links/invoke",
            json_body={},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def link_org_to_entra_tenant(
        self,
        *,
        org_id: str,
        tenant_id: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/tenancy/entra-links",
            json_body={"org_id": org_id, "tenant_id": tenant_id},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    # ------------------------------------------------------------------
    # Secrets manager (admin overhaul Phase 1)
    # ------------------------------------------------------------------

    async def list_secrets(
        self,
        *,
        backend: str | None = None,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if backend:
            params["backend"] = backend
        if namespace:
            params["namespace"] = namespace
        response = await self._request(
            "GET",
            "/admin/secrets",
            params=params or None,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def describe_secret(
        self,
        ref: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/admin/secrets/{ref}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_secret_consumers(
        self,
        ref: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/admin/secrets/{ref}/consumers",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def rotate_secret(
        self,
        ref: str,
        *,
        reason: str,
        notify_consumers: bool,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/admin/secrets/{ref}/rotate",
            json_body={"reason": reason, "notify_consumers": notify_consumers},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    # ------------------------------------------------------------------
    # Lineage explorer (admin overhaul Phase 1)
    # ------------------------------------------------------------------

    async def list_lineage_datasets(
        self,
        *,
        namespace: str | None = None,
        medallion_layer: str | None = None,
        limit: int = 100,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"limit": limit}
        if namespace:
            body["namespace"] = namespace
        if medallion_layer:
            body["medallion_layer"] = medallion_layer
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.lineage.list_datasets/invoke",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def describe_lineage_dataset(
        self,
        urn: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.lineage.describe_dataset/invoke",
            json_body={"urn": urn},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def lineage_ancestry(
        self,
        urn: str,
        *,
        depth: int = 3,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.lineage.ancestry/invoke",
            json_body={"urn": urn, "depth": depth},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def lineage_impact(
        self,
        urn: str,
        *,
        depth: int = 3,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.lineage.impact/invoke",
            json_body={"urn": urn, "depth": depth},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_lineage_transforms(
        self,
        *,
        transform_kind: str | None = None,
        limit: int = 100,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"limit": limit}
        if transform_kind:
            body["transform_kind"] = transform_kind
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.lineage.list_transforms/invoke",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def describe_lineage_transform(
        self,
        transform_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.lineage.describe_transform/invoke",
            json_body={"transform_id": transform_id},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    # ------------------------------------------------------------------
    # MLflow model registry (admin overhaul Phase 1)
    # ------------------------------------------------------------------

    async def list_mlflow_models(
        self,
        *,
        namespace: str | None = None,
        limit: int = 100,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if namespace:
            params["namespace"] = namespace
        response = await self._request(
            "GET",
            "/ml/models",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def describe_mlflow_model(
        self,
        name: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/ml/models/{name}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def list_mlflow_versions(
        self,
        name: str,
        *,
        limit: int = 50,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/ml/models/{name}/versions",
            params={"limit": limit},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def describe_mlflow_version(
        self,
        name: str,
        version: int,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/ml/models/{name}/versions/{version}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def set_mlflow_alias(
        self,
        name: str,
        *,
        alias: str,
        version: int,
        reason: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "PUT",
            f"/ml/models/{name}/aliases/{alias}",
            json_body={"version": version, "reason": reason},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def delete_mlflow_alias(
        self,
        name: str,
        *,
        alias: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "DELETE",
            f"/ml/models/{name}/aliases/{alias}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    # ------------------------------------------------------------------
    # Paper trading (admin overhaul Phase 1)
    # ------------------------------------------------------------------

    async def list_paper_runs(
        self,
        *,
        organization_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if organization_id:
            params["organization_id"] = organization_id
        if status:
            params["status"] = status
        response = await self._request(
            "GET",
            "/paper/runs",
            params=params,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def get_paper_run(
        self,
        run_id: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/paper/runs/{run_id}",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def start_paper_run(
        self,
        *,
        config_name: str,
        dry_run: bool,
        reason: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/paper/runs",
            json_body={
                "config_name": config_name,
                "dry_run": dry_run,
                "reason": reason,
            },
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def stop_paper_run(
        self,
        run_id: str,
        *,
        reason: str,
        cancel_open_orders: bool,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/paper/runs/{run_id}/stop",
            json_body={
                "reason": reason,
                "cancel_open_orders": cancel_open_orders,
            },
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    # ------------------------------------------------------------------
    # RBAC (admin overhaul Phase 1)
    # ------------------------------------------------------------------

    async def list_memberships(
        self,
        *,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        role: str | None = None,
        limit: int = 200,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"limit": limit}
        if organization_id:
            body["organization_id"] = organization_id
        if workspace_id:
            body["workspace_id"] = workspace_id
        if role:
            body["role"] = role
        response = await self._request(
            "POST",
            "/mcp/data/tools/data.tenancy.list_memberships/invoke",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def preview_effective_permissions(
        self,
        *,
        user_id: str,
        org_id: str | None = None,
        workspace_id: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"user_id": user_id}
        if org_id:
            body["org_id"] = org_id
        if workspace_id:
            body["workspace_id"] = workspace_id
        response = await self._request(
            "POST",
            "/admin/rbac/effective",
            json_body=body,
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def grant_membership(
        self,
        *,
        user_id: str,
        role: str,
        scope_kind: str,
        scope_id: str,
        reason: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/admin/rbac/memberships",
            json_body={
                "user_id": user_id,
                "role": role,
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                "reason": reason,
            },
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def revoke_membership(
        self,
        membership_id: str,
        *,
        reason: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "DELETE",
            f"/admin/rbac/memberships/{membership_id}",
            params={"reason": reason},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    # ------------------------------------------------------------------
    # Account mode (admin overhaul Phase 1)
    # ------------------------------------------------------------------

    async def get_account_mode(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/admin/accounts/mode",
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def set_account_mode(
        self,
        *,
        mode: str,
        reason: str,
        operator_pinned: bool,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/admin/accounts/mode",
            json_body={
                "mode": mode,
                "reason": reason,
                "operator_pinned": operator_pinned,
            },
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()

    async def clear_account_mode_pin(
        self,
        *,
        reason: str,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            "DELETE",
            "/admin/accounts/mode/pin",
            params={"reason": reason},
            bearer_passthrough=bearer_passthrough,
        )
        return response.json()


class HaltBroker:
    """Fan-out helper that hits every halt endpoint in parallel."""

    def __init__(
        self,
        *,
        control_plane: ControlPlaneBroker,
        monolith: MonolithBroker,
        monolith_halt_paths: tuple[str, ...] = (
            "/agents/halt",
            "/paper/stop-all",
            "/bots/halt-all",
            "/rl/halt-all",
            "/quant-agents/halt",
            "/workflows/halt",
        ),
    ) -> None:
        self._cp = control_plane
        self._monolith = monolith
        self._monolith_paths = monolith_halt_paths

    async def halt_all(
        self,
        reason: str,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        """Hit every halt endpoint; aggregate results.

        Per-endpoint failures land in ``failures`` instead of raising
        so the KillSwitch always returns a coherent envelope to the
        UI (the operator decides whether to retry).
        """
        results: dict[str, Any] = {"halted": [], "failures": []}
        for label, fn in (
            ("workloads", lambda: self._cp.halt_workloads(reason)),
            ("terraform", lambda: self._cp.halt_terraform(reason)),
        ):
            try:
                results["halted"].append({"target": label, "result": await fn()})
            except AdminBrokerError as exc:
                results["failures"].append(
                    {
                        "target": label,
                        "error": str(exc),
                        "code": exc.code,
                        "status_code": exc.status_code,
                    }
                )
        for path in self._monolith_paths:
            try:
                response = await self._monolith._request(  # noqa: SLF001
                    "POST",
                    path,
                    json_body={"reason": reason},
                    bearer_passthrough=bearer_passthrough,
                )
                results["halted"].append({"target": path, "result": response.json() if response.text else None})
            except AdminBrokerError as exc:
                results["failures"].append(
                    {
                        "target": path,
                        "error": str(exc),
                        "code": exc.code,
                        "status_code": exc.status_code,
                    }
                )
        return results


# ---------------------------------------------------------------------------
# Process-wide cache
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Brokers:
    control_plane: ControlPlaneBroker
    monolith: MonolithBroker
    halt: HaltBroker


_CACHE: _Brokers | None = None
_CACHE_LOCK = threading.Lock()


def build_default_brokers(
    settings: AdminSettings | None = None,
    *,
    secret_stores: tuple[SecretStore, ...] | None = None,
) -> _Brokers:
    settings = settings or get_settings()
    stores = secret_stores or (EnvSecretStore(),)
    cp_audience = settings.m2m_cp_audience
    cp_m2m = M2MTokenBroker(
        M2MTokenBrokerConfig(
            provider_alias=settings.auth_provider,
            tenant=settings.auth_entra_tenant,
            credential_key=CredentialKey(
                service=settings.m2m_credential_service,
                purpose=settings.m2m_credential_purpose,
            ),
        ),
        secret_stores=stores,
        provider=MsalEntraValidator(
            tenant=settings.auth_entra_tenant,
            audience=cp_audience,
        ),
    )
    monolith_audience = "api://aqp-monolith"
    monolith_m2m = M2MTokenBroker(
        M2MTokenBrokerConfig(
            provider_alias=settings.auth_provider,
            tenant=settings.auth_entra_tenant,
            credential_key=CredentialKey(
                service="aqp-admin-to-monolith",
                purpose=settings.m2m_credential_purpose,
            ),
        ),
        secret_stores=stores,
        provider=MsalEntraValidator(
            tenant=settings.auth_entra_tenant,
            audience=monolith_audience,
        ),
    )
    cp = ControlPlaneBroker(
        m2m=cp_m2m,
        http=_BrokerHttpClient(
            base_url=settings.control_plane_url,
            audience=cp_audience,
        ),
    )
    monolith = MonolithBroker(
        m2m=monolith_m2m,
        http=_BrokerHttpClient(
            base_url=settings.api_url,
            audience=monolith_audience,
        ),
    )
    return _Brokers(
        control_plane=cp,
        monolith=monolith,
        halt=HaltBroker(control_plane=cp, monolith=monolith),
    )


def get_brokers() -> _Brokers:
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            _CACHE = build_default_brokers()
    return _CACHE


def reset_brokers() -> None:
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = None


__all__ = [
    "AdminBrokerError",
    "ControlPlaneBroker",
    "EnvSecretStore",
    "HaltBroker",
    "MonolithBroker",
    "build_default_brokers",
    "get_brokers",
    "reset_brokers",
]
