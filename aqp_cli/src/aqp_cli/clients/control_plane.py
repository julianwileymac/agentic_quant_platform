"""HTTP wrapper around the AQP control plane (`/manage/*`)."""

from __future__ import annotations

from typing import Any

import httpx


class ControlPlaneClient:
    """Thin httpx wrapper for the control plane API."""

    def __init__(self, base_url: str, timeout: float = 15.0, access_token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        headers = {"Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        """Execute an HTTP request and return decoded JSON when possible."""
        resp = self._client.request(method, path, params=params, json=json_body)
        resp.raise_for_status()
        if not resp.content:
            return {}
        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            return resp.json()
        return {"text": resp.text}

    def _unwrap_envelope(self, payload: Any) -> Any:
        if (
            isinstance(payload, dict)
            and "data" in payload
            and payload.get("status") in {"ok", "queued"}
        ):
            return payload["data"]
        return payload

    def list_topology_services(self) -> list[dict[str, Any]]:
        """Call `GET /manage/topology/services`."""
        payload = self.request("GET", "/manage/topology/services")
        data = self._unwrap_envelope(payload)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        services = data.get("services", []) if isinstance(data, dict) else []
        return [item for item in services if isinstance(item, dict)]

    def service_status(self, service_id: str, *, namespace: str | None = None) -> dict[str, Any]:
        payload = self.request(
            "GET",
            f"/manage/deployments/{service_id}",
            params={"namespace": namespace} if namespace else None,
        )
        data = self._unwrap_envelope(payload)
        return data if isinstance(data, dict) else {"value": data}

    def list_deployments(self, *, namespace: str | None = None) -> list[dict[str, Any]]:
        payload = self.request(
            "GET",
            "/manage/deployments",
            params={"namespace": namespace} if namespace else None,
        )
        data = self._unwrap_envelope(payload)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
