"""Thin httpx wrapper around the HCP Terraform (formerly Terraform Cloud) HTTP API.

Used when ``settings.terraform_state_backend == "hcp"``. Implements
just the endpoints the runtime actually needs:

- workspace list / create / show
- configuration version create + upload
- run create / show / apply / cancel
- state version list / show (URL only — payload pull is on-demand)

Modeled on the ``python-terrasnek`` shape but written from scratch so
AQP doesn't take a hard dep on a third-party SDK. Authentication
uses the ``Bearer <AQP_HCP_TOKEN>`` header.

Reference: https://developer.hashicorp.com/terraform/cloud-docs/api-docs
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HcpClientError(RuntimeError):
    """Raised on HCP API errors that the caller should surface to the UI."""


class HcpClient:
    """Synchronous httpx client for HCP Terraform / Terraform Enterprise."""

    def __init__(
        self,
        token: str | None = None,
        organization: str | None = None,
        api_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token_override = token
        self._org_override = organization
        self._api_url_override = api_url
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _settings(self) -> Any | None:
        try:
            from aqp.config import settings

            return settings
        except Exception:
            return None

    @property
    def token(self) -> str:
        if self._token_override:
            return self._token_override
        s = self._settings()
        return str(getattr(s, "hcp_token", "") or "")

    @property
    def organization(self) -> str:
        if self._org_override:
            return self._org_override
        s = self._settings()
        return str(getattr(s, "hcp_organization", "") or "")

    @property
    def api_url(self) -> str:
        if self._api_url_override:
            return self._api_url_override
        s = self._settings()
        return str(
            getattr(s, "hcp_api_url", "https://app.terraform.io/api/v2")
            or "https://app.terraform.io/api/v2"
        )

    def is_configured(self) -> bool:
        return bool(self.token and self.organization)

    def _client(self) -> httpx.Client:
        if not self.token:
            raise HcpClientError(
                "HCP token is not configured (set AQP_HCP_TOKEN)"
            )
        return httpx.Client(
            base_url=self.api_url,
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/vnd.api+json",
            },
        )

    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    def list_workspaces(self) -> list[dict[str, Any]]:
        org = self.organization or ""
        if not org:
            raise HcpClientError("HCP organization not configured (set AQP_HCP_ORGANIZATION)")
        with self._client() as client:
            resp = client.get(f"/organizations/{org}/workspaces")
            _raise_for_status(resp)
            data = resp.json().get("data") or []
            return [_serialize_workspace(item) for item in data]

    def get_workspace(self, name: str) -> dict[str, Any] | None:
        org = self.organization or ""
        if not org:
            raise HcpClientError("HCP organization not configured")
        with self._client() as client:
            resp = client.get(f"/organizations/{org}/workspaces/{name}")
            if resp.status_code == 404:
                return None
            _raise_for_status(resp)
            return _serialize_workspace(resp.json().get("data") or {})

    def create_workspace(
        self,
        name: str,
        *,
        execution_mode: str = "remote",
        terraform_version: str | None = None,
        auto_apply: bool = False,
        working_directory: str | None = None,
    ) -> dict[str, Any]:
        org = self.organization or ""
        if not org:
            raise HcpClientError("HCP organization not configured")
        attributes: dict[str, Any] = {
            "name": name,
            "execution-mode": execution_mode,
            "auto-apply": bool(auto_apply),
        }
        if terraform_version:
            attributes["terraform-version"] = terraform_version
        if working_directory:
            attributes["working-directory"] = working_directory
        body = {"data": {"type": "workspaces", "attributes": attributes}}
        with self._client() as client:
            resp = client.post(f"/organizations/{org}/workspaces", json=body)
            _raise_for_status(resp)
            return _serialize_workspace(resp.json().get("data") or {})

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def create_run(
        self,
        workspace_id: str,
        *,
        is_destroy: bool = False,
        auto_apply: bool = False,
        message: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "data": {
                "type": "runs",
                "attributes": {
                    "is-destroy": bool(is_destroy),
                    "message": message or "Triggered by AQP TerraformRuntime",
                    "auto-apply": bool(auto_apply),
                },
                "relationships": {
                    "workspace": {
                        "data": {"type": "workspaces", "id": workspace_id}
                    },
                },
            }
        }
        with self._client() as client:
            resp = client.post("/runs", json=body)
            _raise_for_status(resp)
            return _serialize_run(resp.json().get("data") or {})

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._client() as client:
            resp = client.get(f"/runs/{run_id}")
            if resp.status_code == 404:
                return None
            _raise_for_status(resp)
            return _serialize_run(resp.json().get("data") or {})

    def list_runs(
        self, workspace_id: str, *, limit: int = 25
    ) -> list[dict[str, Any]]:
        with self._client() as client:
            resp = client.get(
                f"/workspaces/{workspace_id}/runs",
                params={"page[size]": int(limit)},
            )
            _raise_for_status(resp)
            return [
                _serialize_run(item)
                for item in (resp.json().get("data") or [])
            ]

    def apply_run(self, run_id: str, comment: str | None = None) -> None:
        body = {"comment": comment or "Approved via AQP TerraformRuntime"}
        with self._client() as client:
            resp = client.post(f"/runs/{run_id}/actions/apply", json=body)
            _raise_for_status(resp, allow_status={202, 204})

    def cancel_run(self, run_id: str, comment: str | None = None) -> None:
        body = {"comment": comment or "Cancelled via AQP TerraformRuntime"}
        with self._client() as client:
            resp = client.post(f"/runs/{run_id}/actions/cancel", json=body)
            _raise_for_status(resp, allow_status={202, 204})

    def discard_run(self, run_id: str, comment: str | None = None) -> None:
        body = {"comment": comment or "Discarded via AQP TerraformRuntime"}
        with self._client() as client:
            resp = client.post(f"/runs/{run_id}/actions/discard", json=body)
            _raise_for_status(resp, allow_status={202, 204})

    # ------------------------------------------------------------------
    # State versions
    # ------------------------------------------------------------------

    def list_state_versions(
        self,
        workspace_id: str,
        *,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        org = self.organization or ""
        if not org:
            raise HcpClientError("HCP organization not configured")
        with self._client() as client:
            # The HCP endpoint expects ``filter[workspace][name]`` because
            # there's no direct ``/workspaces/<id>/state-versions`` route.
            workspace = self._workspace_name_by_id(client, workspace_id)
            if not workspace:
                return []
            resp = client.get(
                "/state-versions",
                params={
                    "filter[organization][name]": org,
                    "filter[workspace][name]": workspace,
                    "page[size]": int(limit),
                },
            )
            _raise_for_status(resp)
            return [
                _serialize_state_version(item)
                for item in (resp.json().get("data") or [])
            ]

    def _workspace_name_by_id(
        self,
        client: httpx.Client,
        workspace_id: str,
    ) -> str | None:
        resp = client.get(f"/workspaces/{workspace_id}")
        if resp.status_code == 404:
            return None
        _raise_for_status(resp)
        attrs = (resp.json().get("data") or {}).get("attributes") or {}
        return attrs.get("name")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raise_for_status(
    resp: httpx.Response,
    *,
    allow_status: set[int] | None = None,
) -> None:
    allow = allow_status or set()
    if resp.status_code in allow:
        return
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = {"text": resp.text[:512]}
        raise HcpClientError(
            f"HCP API {resp.status_code} {resp.request.method} {resp.request.url}: {payload}"
        )


def _serialize_workspace(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes") or {}
    return {
        "id": item.get("id"),
        "name": attrs.get("name"),
        "execution_mode": attrs.get("execution-mode"),
        "terraform_version": attrs.get("terraform-version"),
        "auto_apply": attrs.get("auto-apply"),
        "working_directory": attrs.get("working-directory"),
        "created_at": attrs.get("created-at"),
        "updated_at": attrs.get("updated-at"),
        "locked": attrs.get("locked"),
        "raw": item,
    }


def _serialize_run(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes") or {}
    return {
        "id": item.get("id"),
        "status": attrs.get("status"),
        "message": attrs.get("message"),
        "is_destroy": attrs.get("is-destroy"),
        "has_changes": attrs.get("has-changes"),
        "auto_apply": attrs.get("auto-apply"),
        "created_at": attrs.get("created-at"),
        "raw": item,
    }


def _serialize_state_version(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes") or {}
    return {
        "id": item.get("id"),
        "serial": attrs.get("serial"),
        "lineage": attrs.get("lineage"),
        "created_at": attrs.get("created-at"),
        "size": attrs.get("size"),
        "hosted_state_download_url": attrs.get("hosted-state-download-url"),
        "raw": item,
    }


__all__ = ["HcpClient", "HcpClientError"]
