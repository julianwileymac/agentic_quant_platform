"""HTTP client for USPTO endpoints.

Three sub-APIs are supported through a single client:

- **PatentsView** (https://search.patentsview.org/api/v1) — granted
  patents and applications. Requires an API key passed via the
  ``X-Api-Key`` header.
- **PEDS** (https://ped.uspto.gov/api) — patent application data,
  including assignments. JSON; no key required for low-volume use.
- **TSDR** (https://tsdrapi.uspto.gov/ts/cd/casestatus) — trademark
  case status (XML by default; we request JSON via
  ``Accept: application/json`` and fall back to XML parsing when the
  endpoint refuses).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


class UsptoClientError(RuntimeError):
    """Raised on USPTO HTTP errors."""


class UsptoClient:
    """Tri-API USPTO client (PatentsView + PEDS + TSDR)."""

    def __init__(
        self,
        *,
        patentsview_url: str | None = None,
        peds_url: str | None = None,
        tsdr_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.patentsview_url = (patentsview_url or settings.uspto_patentsview_url).rstrip("/")
        self.peds_url = (peds_url or settings.uspto_peds_url).rstrip("/")
        self.tsdr_url = (tsdr_url or settings.uspto_tsdr_url).rstrip("/")
        self.api_key = api_key or settings.uspto_api_key or ""
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout, headers={"User-Agent": "aqp-research/0.1"})

    def __enter__(self) -> "UsptoClient":
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
            r = self._http.get(self.patentsview_url + "/patent/")
            return 200 <= r.status_code < 500, f"patentsview http {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # ------------------------------------------------------------------ PatentsView
    def patents(
        self,
        *,
        query: dict[str, Any],
        fields: list[str] | None = None,
        page: int = 1,
        per_page: int = 100,
        sort: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.patentsview_url}/patent/"
        body: dict[str, Any] = {
            "q": query,
            "f": fields or [
                "patent_id",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "patent_type",
                "assignees.assignee_organization",
                "inventors.inventor_name_first",
                "inventors.inventor_name_last",
                "application.filing_date",
            ],
            "o": {"page": int(page), "per_page": min(int(per_page), 1000)},
        }
        if sort:
            body["s"] = sort
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        try:
            r = self._http.post(url, json=body, headers=headers)
        except Exception as exc:  # noqa: BLE001
            raise UsptoClientError(f"PatentsView request failed: {exc}") from exc
        if r.status_code >= 400:
            raise UsptoClientError(f"PatentsView returned HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def iter_patents(
        self,
        *,
        query: dict[str, Any],
        fields: list[str] | None = None,
        per_page: int = 100,
        max_records: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        page = 1
        emitted = 0
        while True:
            payload = self.patents(query=query, fields=fields, page=page, per_page=per_page)
            patents = payload.get("patents") or []
            if not patents:
                return
            for p in patents:
                yield p
                emitted += 1
                if max_records is not None and emitted >= max_records:
                    return
            if len(patents) < per_page:
                return
            page += 1

    # ------------------------------------------------------------------ PEDS (assignments)
    def assignments(
        self,
        *,
        searchText: str,
        rows: int = 100,
        start: int = 0,
    ) -> dict[str, Any]:
        url = f"{self.peds_url}/queries"
        params = {
            "searchText": searchText,
            "df": "appEarliestPubDate",
            "rows": min(int(rows), 1000),
            "start": int(start),
        }
        try:
            r = self._http.get(url, params=params, headers={"Accept": "application/json"})
        except Exception as exc:  # noqa: BLE001
            raise UsptoClientError(f"PEDS request failed: {exc}") from exc
        if r.status_code >= 400:
            raise UsptoClientError(f"PEDS returned HTTP {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except Exception:
            return {"queryResults": {}}

    # ------------------------------------------------------------------ TSDR (trademarks)
    def trademark_case_status(self, *, serial_number: str) -> dict[str, Any]:
        url = f"{self.tsdr_url}/sn{serial_number}/info.json"
        try:
            r = self._http.get(url, headers={"Accept": "application/json"})
        except Exception as exc:  # noqa: BLE001
            raise UsptoClientError(f"TSDR request failed: {exc}") from exc
        if r.status_code >= 400:
            raise UsptoClientError(f"TSDR returned HTTP {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except Exception:
            return {"raw_xml": r.text}


__all__ = ["UsptoClient", "UsptoClientError"]
