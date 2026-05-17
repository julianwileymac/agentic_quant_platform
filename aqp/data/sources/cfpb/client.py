"""HTTP client for the CFPB Consumer Complaint Database public API.

The public search endpoint is documented at
https://cfpb.github.io/api/ccdb/. It serves Elasticsearch-style JSON
and accepts pagination via ``frm`` (offset) + ``size`` (page size, max
1000). The legacy bulk CSV at
https://files.consumerfinance.gov/ccdb/complaints.csv.zip is supported
indirectly via the generic ingestion pipeline; this client targets the
incremental REST surface.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


class CfpbClientError(RuntimeError):
    """Raised when the CFPB API returns a non-2xx response."""


class CfpbClient:
    """Thin synchronous client for the CFPB CCDB search endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        user_agent: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or settings.cfpb_api_url).rstrip("/")
        self.user_agent = user_agent or settings.cfpb_user_agent
        self.timeout = timeout
        self._http = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )

    def __enter__(self) -> "CfpbClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ probe
    def probe(self) -> tuple[bool, str]:
        try:
            r = self._http.get(f"{self.base_url}/", params={"size": 1})
            ok = 200 <= r.status_code < 400
            return ok, f"http {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # ------------------------------------------------------------------ search
    def search_page(
        self,
        *,
        company: str | None = None,
        product: str | None = None,
        date_received_min: str | None = None,
        date_received_max: str | None = None,
        has_narrative: bool | None = None,
        size: int = 100,
        frm: int = 0,
        sort: str = "created_date_desc",
    ) -> dict[str, Any]:
        """Return one page of results (raw JSON) from the search API."""
        params: dict[str, Any] = {"size": min(int(size), 1000), "frm": int(frm), "sort": sort, "format": "json"}
        if company:
            params["company"] = company
        if product:
            params["product"] = product
        if date_received_min:
            params["date_received_min"] = date_received_min
        if date_received_max:
            params["date_received_max"] = date_received_max
        if has_narrative:
            params["has_narrative"] = "true"
        try:
            r = self._http.get(f"{self.base_url}/", params=params)
        except Exception as exc:  # noqa: BLE001
            raise CfpbClientError(f"CFPB request failed: {exc}") from exc
        if r.status_code >= 400:
            raise CfpbClientError(f"CFPB returned HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def iter_complaints(
        self,
        *,
        company: str | None = None,
        product: str | None = None,
        date_received_min: str | None = None,
        date_received_max: str | None = None,
        has_narrative: bool | None = None,
        page_size: int = 500,
        max_records: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield complaint hits one at a time, paging until the API runs out."""
        emitted = 0
        offset = 0
        while True:
            page = self.search_page(
                company=company,
                product=product,
                date_received_min=date_received_min,
                date_received_max=date_received_max,
                has_narrative=has_narrative,
                size=page_size,
                frm=offset,
            )
            hits_root = page.get("hits") or {}
            hits = hits_root.get("hits") if isinstance(hits_root, dict) else hits_root
            if not hits:
                return
            for hit in hits:
                source = hit.get("_source") if isinstance(hit, dict) else None
                if source is None and isinstance(hit, dict):
                    source = hit
                if not isinstance(source, dict):
                    continue
                yield source
                emitted += 1
                if max_records is not None and emitted >= max_records:
                    return
            if len(hits) < page_size:
                return
            offset += page_size


__all__ = ["CfpbClient", "CfpbClientError"]
