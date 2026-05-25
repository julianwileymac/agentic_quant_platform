"""DataHub client wrapper.

Wraps both the ``acryl-datahub`` SDK (when installed) and the GMS
REST endpoint. The SDK gives us nice typed emitters for
Dataset/DataFlow/DataJob, while the REST endpoint covers
metadata-search and ingestion-recipe queries.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from aqp.config import settings
from aqp.credentials import get_datahub_credential

logger = logging.getLogger(__name__)


class DataHubUnavailableError(RuntimeError):
    """Raised when neither the SDK nor the REST endpoint is reachable."""


class DataHubClient:
    """Lightweight wrapper exposing both REST and SDK helpers."""

    def __init__(
        self,
        *,
        gms_url: str | None = None,
        token: str | None = None,
        env: str | None = None,
    ) -> None:
        # AGENTS Rule 26 — credentials flow through CredentialResolver.
        # The explicit kwargs win (test injection); when unset we ask
        # the resolver, which will hit M2M / Vault / file stores before
        # falling back to the bootstrap env value.
        cred = get_datahub_credential()
        self.gms_url = (
            gms_url or cred.get("gms_url") or settings.datahub_gms_url or ""
        ).rstrip("/")
        self.token = token or cred.get("token", "") or ""
        self.env = env or cred.get("env") or settings.datahub_env or "PROD"

    # ------------------------------------------------------------------
    # Reachability
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.gms_url)

    def ping(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "reason": "datahub_gms_url unset"}
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self.gms_url}/config",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return {"ok": True, "config": resp.json()}
        except Exception as exc:  # noqa: BLE001
            logger.debug("datahub ping failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # SDK accessors
    # ------------------------------------------------------------------

    def emitter(self) -> Any:
        try:
            from datahub.emitter.rest_emitter import DatahubRestEmitter
        except Exception as exc:  # noqa: BLE001 - optional dep
            raise DataHubUnavailableError(
                f"acryl-datahub SDK not installed: {exc}"
            ) from exc
        if not self.is_configured():
            raise DataHubUnavailableError("datahub_gms_url not configured")
        return DatahubRestEmitter(
            gms_server=self.gms_url,
            token=self.token or None,
        )

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def search(
        self,
        *,
        query: str,
        entity: str = "dataset",
        start: int = 0,
        count: int = 20,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {"results": [], "error": "datahub_gms_url unset"}
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{self.gms_url}/entities",
                    params={
                        "action": "search",
                        "input": query,
                        "entity": entity,
                        "start": start,
                        "count": count,
                    },
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("datahub search failed: %s", exc)
            return {"results": [], "error": str(exc)}

    def get_entity(self, urn: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"error": "datahub_gms_url unset"}
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{self.gms_url}/entities/{urn}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("datahub get_entity %s failed: %s", urn, exc)
            return {"error": str(exc)}


_client_singleton: DataHubClient | None = None


def get_client() -> DataHubClient:
    """Cached :class:`DataHubClient` shared across the process."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = DataHubClient()
    return _client_singleton


__all__ = ["DataHubClient", "DataHubUnavailableError", "get_client"]
