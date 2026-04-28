"""Thin Airbyte API client used by routes, workers, and Dagster resources."""
from __future__ import annotations

import time
from typing import Any

import httpx

from aqp.config import settings
from aqp.data.airbyte.models import SyncStatus
from aqp.observability.airbyte import airbyte_span


class AirbyteClientError(RuntimeError):
    """Raised when the Airbyte API returns an error response."""


class AirbyteClient:
    """Small wrapper around Airbyte's public API.

    The client keeps endpoint construction isolated so tests can mock HTTP
    without booting Airbyte. Methods return JSON dictionaries directly to
    avoid binding AQP to one Airbyte API minor version.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_url: str | None = None,
        token: str | None = None,
        workspace_id: str | None = None,
        timeout: float | None = None,
    ) -> None:
        root = (api_url or settings.airbyte_api_url or base_url or settings.airbyte_base_url).rstrip("/")
        self.base_url = root
        self.token = token if token is not None else settings.airbyte_auth_token
        self.workspace_id = workspace_id if workspace_id is not None else settings.airbyte_workspace_id
        self.timeout = timeout if timeout is not None else settings.airbyte_request_timeout_seconds

    def health(self) -> dict[str, Any]:
        for path in ("/api/public/v1/health", "/api/v1/health", "/health"):
            try:
                return self._request("GET", path)
            except AirbyteClientError:
                continue
        return {"ok": False, "error": "Airbyte health endpoint unavailable"}

    def list_workspaces(self) -> dict[str, Any]:
        return self._request("GET", "/api/public/v1/workspaces")

    def list_sources(self) -> dict[str, Any]:
        return self._request("GET", "/api/public/v1/sources", query=self._workspace_query())

    def list_destinations(self) -> dict[str, Any]:
        return self._request("GET", "/api/public/v1/destinations", query=self._workspace_query())

    def list_connections(self) -> dict[str, Any]:
        return self._request("GET", "/api/public/v1/connections", query=self._workspace_query())

    def create_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/public/v1/sources", json=self._with_workspace(payload))

    def create_destination(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/public/v1/destinations", json=self._with_workspace(payload))

    def create_connection(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/public/v1/connections", json=payload)

    def discover_source_schema(self, source_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/public/v1/sources/{source_id}/discover_schema",
            json={},
        )

    def trigger_sync(self, connection_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/public/v1/jobs",
            json={"connectionId": connection_id, "jobType": "sync"},
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/public/v1/jobs/{job_id}")

    def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval_seconds: float | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        interval = poll_interval_seconds or settings.airbyte_poll_interval_seconds
        timeout = timeout_seconds or settings.airbyte_sync_timeout_seconds
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.get_job(job_id)
            status = normalize_job_status(last).value
            if status in {"succeeded", "failed", "cancelled"}:
                return last
            time.sleep(interval)
        raise AirbyteClientError(f"Airbyte job {job_id} did not finish within {timeout}s")

    def _workspace_query(self) -> dict[str, str]:
        return {"workspaceIds": self.workspace_id} if self.workspace_id else {}

    def _with_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        if self.workspace_id and "workspaceId" not in body:
            body["workspaceId"] = self.workspace_id
        return body

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = f"{self.base_url}{path}"
        with airbyte_span("airbyte.http", method=method, path=path):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(method, url, json=json, params=query, headers=headers)
                    response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise AirbyteClientError(f"{method} {path} failed: {exc.response.text}") from exc
            except httpx.HTTPError as exc:
                raise AirbyteClientError(f"{method} {path} failed: {exc}") from exc
        if response.status_code == 204:
            return {}
        try:
            data = response.json()
        except ValueError:
            return {"text": response.text}
        return data if isinstance(data, dict) else {"data": data}


def normalize_job_status(payload: dict[str, Any]) -> SyncStatus:
    """Normalize Airbyte job status payloads across API variants."""
    raw = (
        payload.get("status")
        or (payload.get("job") or {}).get("status")
        or payload.get("jobStatus")
        or ""
    )
    value = str(raw).strip().lower()
    mapping = {
        "pending": SyncStatus.PENDING,
        "incomplete": SyncStatus.RUNNING,
        "running": SyncStatus.RUNNING,
        "syncing": SyncStatus.RUNNING,
        "succeeded": SyncStatus.SUCCEEDED,
        "success": SyncStatus.SUCCEEDED,
        "failed": SyncStatus.FAILED,
        "error": SyncStatus.FAILED,
        "cancelled": SyncStatus.CANCELLED,
        "canceled": SyncStatus.CANCELLED,
    }
    return mapping.get(value, SyncStatus.UNKNOWN)


def extract_job_id(payload: dict[str, Any]) -> str | None:
    """Pull a job id from common Airbyte response shapes."""
    candidates = [
        payload.get("jobId"),
        payload.get("id"),
        (payload.get("job") or {}).get("id"),
        (payload.get("job") or {}).get("jobId"),
    ]
    for candidate in candidates:
        if candidate is not None:
            return str(candidate)
    return None


__all__ = [
    "AirbyteClient",
    "AirbyteClientError",
    "extract_job_id",
    "normalize_job_status",
]
