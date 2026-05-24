"""HTTP wrapper around the AQP control plane (`/manage/*`, `/auth/*`).

Primary auth path per AQP rule 27. Never imports `aqp_cp.*` source — talks
over HTTP only so the CLI can ship independently.
"""
from __future__ import annotations

from typing import Any

import httpx


class ControlPlaneClient:
    """Thin httpx wrapper for the control plane API."""

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def list_topology_services(self) -> list[dict[str, Any]]:
        """Call `GET /manage/topology/services` (stub-safe: returns [] on 404)."""
        try:
            resp = self._client.get("/manage/topology/services")
            resp.raise_for_status()
        except httpx.HTTPError:
            return []
        data = resp.json()
        if isinstance(data, list):
            return [s for s in data if isinstance(s, dict)]
        services = data.get("services", []) if isinstance(data, dict) else []
        return [s for s in services if isinstance(s, dict)]

    def device_code_login(self) -> str | None:
        """Initiate a device-code flow via `/auth/device/code` (stub)."""
        return None

    def whoami(self) -> dict[str, Any] | None:
        """Return the authenticated principal via `/auth/me` (stub)."""
        return None

    def close(self) -> None:
        self._client.close()
