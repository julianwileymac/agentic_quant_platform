"""HTTP client for the openFDA API.

Endpoints we use:

- ``/drug/drugsfda.json``           — drug applications (NDA / ANDA / BLA / OTC).
- ``/device/510k.json``             — 510(k) device clearances.
- ``/device/pma.json``              — pre-market approvals.
- ``/drug/event.json``              — FAERS adverse events.
- ``/device/event.json``            — MAUDE adverse events.
- ``/drug/enforcement.json``        — drug recalls.
- ``/device/enforcement.json``      — device recalls.
- ``/food/enforcement.json``        — food recalls.

API key is optional (rate limit is higher with one). Documented at
https://open.fda.gov/apis/.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


class FdaClientError(RuntimeError):
    """Raised on non-2xx FDA responses."""


class FdaClient:
    """Synchronous openFDA client."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or settings.fda_base_url).rstrip("/")
        self.api_key = api_key or settings.fda_api_key or ""
        self.timeout = timeout
        self._http = httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "aqp-research/0.1"},
        )

    def __enter__(self) -> "FdaClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:  # pragma: no cover
            pass

    def probe(self) -> tuple[bool, str]:
        try:
            r = self._http.get(f"{self.base_url}/drug/drugsfda.json", params={"limit": 1})
            return 200 <= r.status_code < 400, f"http {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def search(
        self,
        path: str,
        *,
        search: str | None = None,
        limit: int = 100,
        skip: int = 0,
        sort: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(int(limit), 1000), "skip": int(skip)}
        if search:
            params["search"] = search
        if sort:
            params["sort"] = sort
        if self.api_key:
            params["api_key"] = self.api_key
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            r = self._http.get(url, params=params)
        except Exception as exc:  # noqa: BLE001
            raise FdaClientError(f"FDA request failed: {exc}") from exc
        if r.status_code == 404:
            return {"results": []}
        if r.status_code >= 400:
            raise FdaClientError(f"FDA returned HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def iter_results(
        self,
        path: str,
        *,
        search: str | None = None,
        page_size: int = 100,
        max_records: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        emitted = 0
        skip = 0
        while True:
            page = self.search(path, search=search, limit=page_size, skip=skip)
            results = page.get("results") or []
            if not results:
                return
            for r in results:
                yield r
                emitted += 1
                if max_records is not None and emitted >= max_records:
                    return
            if len(results) < page_size:
                return
            skip += page_size
            # openFDA hard cap on skip is 25_000 + page_size; respect it.
            if skip + page_size > 25000:
                return


__all__ = ["FdaClient", "FdaClientError"]
