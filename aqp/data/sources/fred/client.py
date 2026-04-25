"""Thin HTTP client over the FRED REST API.

The FRED API is free but requires a key (``AQP_FRED_API_KEY``). The
``fredapi`` Python package wraps it nicely; when that isn't installed,
this client uses plain :mod:`httpx` so the base install continues to
work.

All entry points return plain dicts / lists of dicts to keep the
adapter layer free of vendor-specific types.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from aqp.config import settings

logger = logging.getLogger(__name__)


_FRED_BASE = "https://api.stlouisfed.org/fred"


class FredClientError(RuntimeError):
    """Raised when the FRED API returns an error or is misconfigured."""


class FredClient:
    """Minimal synchronous client for the FRED REST API.

    Parameters
    ----------
    api_key:
        Override for ``settings.fred_api_key``. Useful in tests.
    timeout:
        Per-request timeout in seconds.
    base_url:
        Override the API base URL (swap to a mirror for testing).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        base_url: str = _FRED_BASE,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.fred_api_key
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
    )
    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        if not self.api_key:
            raise FredClientError(
                "FRED API key is not configured; set AQP_FRED_API_KEY in the environment"
            )
        query = {k: v for k, v in params.items() if v is not None}
        query.setdefault("api_key", self.api_key)
        query.setdefault("file_type", "json")
        url = f"{self.base_url}/{path.lstrip('/')}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, params=query)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Public surface (matching fred/ REST endpoints)
    # ------------------------------------------------------------------

    def probe(self) -> tuple[bool, str]:
        """Cheap reachability check using the tiny ``fred/category`` endpoint."""
        if not self.api_key:
            return False, "AQP_FRED_API_KEY is not set"
        try:
            self._get("category", category_id=0)
        except FredClientError as exc:
            return False, str(exc)
        except httpx.HTTPError as exc:
            return False, f"FRED probe failed: {exc}"
        return True, "ok"

    def search_series(
        self,
        query: str,
        *,
        limit: int = 25,
        order_by: str = "popularity",
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Search for series matching ``query``.

        Maps to ``fred/series/search``.
        """
        payload = self._get(
            "series/search",
            search_text=query,
            limit=limit,
            order_by=order_by,
            sort_order=sort_order,
        )
        return list(payload.get("seriess") or [])

    def get_series(self, series_id: str) -> dict[str, Any] | None:
        """Return the metadata record for a single series."""
        payload = self._get("series", series_id=series_id)
        records = payload.get("seriess") or []
        return records[0] if records else None

    def get_observations(
        self,
        series_id: str,
        *,
        observation_start: str | None = None,
        observation_end: str | None = None,
        units: str | None = None,
        frequency: str | None = None,
        aggregation_method: str | None = None,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return raw observations as a list of dicts.

        Maps to ``fred/series/observations``. Each dict has ``date``,
        ``value``, ``realtime_start`` and ``realtime_end`` keys.
        """
        payload = self._get(
            "series/observations",
            series_id=series_id,
            observation_start=observation_start,
            observation_end=observation_end,
            units=units,
            frequency=frequency,
            aggregation_method=aggregation_method,
            realtime_start=realtime_start,
            realtime_end=realtime_end,
        )
        return list(payload.get("observations") or [])
