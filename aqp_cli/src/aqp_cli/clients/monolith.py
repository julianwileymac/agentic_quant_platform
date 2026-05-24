"""HTTP wrapper for AQP monolith routes (`/auth`, `/me`, `/configs`, etc.)."""

from __future__ import annotations

from typing import Any

import httpx


class MonolithClient:
    """Thin JSON client for the AQP API."""

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
        headers: dict[str, str] | None = None,
        files: Any | None = None,
    ) -> Any:
        resp = self._client.request(
            method,
            path,
            params=params,
            json=json_body,
            headers=headers,
            files=files,
        )
        resp.raise_for_status()
        if not resp.content:
            return {}
        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            return resp.json()
        return {"text": resp.text}
