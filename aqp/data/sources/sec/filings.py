"""SEC filings adapter backed by :mod:`edgartools`."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.config import settings
from aqp.data.catalog import register_data_links, register_dataset_version
from aqp.data.sources.base import (
    DataSourceAdapter,
    IdentifierSpec,
    ObservationsResult,
    ProbeResult,
)
from aqp.data.sources.domains import DataDomain
from aqp.data.sources.resolvers.identifiers import IdentifierResolver
from aqp.data.sources.sec.catalog import upsert_sec_filing
from aqp.data.sources.sec.client import SecClient, SecClientError
from aqp.data.sources.sec.xbrl import (
    fund_holdings,
    insider_transactions,
    standardize_financials,
)

logger = logging.getLogger(__name__)


class SecFilingsAdapter(DataSourceAdapter):
    """Adapter for SEC EDGAR filings (``10-K``, ``10-Q``, ``8-K``, ``4``, ``13F-HR``, ...)."""

    source_key = "sec_edgar"
    display_name = "SEC EDGAR"
    domain = DataDomain.FILINGS_INDEX

    def __init__(
        self,
        client: SecClient | None = None,
        *,
        parquet_root: Path | str | None = None,
    ) -> None:
        self.client = client or SecClient()
        root = parquet_root or (settings.parquet_dir / "sec")
        self.parquet_root = Path(root)

    # ------------------------------------------------------------------
    # DataSourceAdapter API
    # ------------------------------------------------------------------

    def probe(self) -> ProbeResult:
        ok, message = self.client.probe()
        return ProbeResult.success(message) if ok else ProbeResult.failure(message)

    def fetch_metadata(
        self,
        *,
        cik_or_ticker: str | int,
        form: str | list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int | None = 50,
    ) -> dict[str, Any]:
        """List filings for a company; persists summary rows into ``sec_filings``."""
        filings = self.client.get_filings(
            cik_or_ticker=cik_or_ticker,
            form=form,
            start=start,
            end=end,
            limit=limit,
        )
        rows = self._filings_to_rows(filings)
        resolver = IdentifierResolver(source_name=self.source_key)
        for record in rows:
            upsert_sec_filing(record)
            if record.get("cik") and record.get("instrument_vt_symbol"):
                resolver.upsert_links(
                    [
                        IdentifierSpec(
                            scheme="cik",
                            value=record["cik"],
                            entity_kind="instrument",
                            instrument_vt_symbol=record["instrument_vt_symbol"],
                            meta={"ticker": record.get("ticker")},
                        )
                    ]
                )
        return {
            "cik_or_ticker": str(cik_or_ticker),
            "count": len(rows),
            "filings": rows,
        }

    def fetch_observations(
        self,
        *,
        cik_or_ticker: str | int,
        artifact: str = "financials",
        form: str | None = None,
        start: str | None = None,
        end: str | None = None,
        persist: bool = True,
    ) -> ObservationsResult:
        """Fetch a specific parsed artifact and return a tidy frame.

        ``artifact`` values: ``"financials"`` (balance sheet + IS + CF),
        ``"insider"`` (Form 4 transactions), ``"holdings"`` (13F).
        """
        artifact = artifact.lower()
        if artifact == "financials":
            return self._fetch_financials(
                cik_or_ticker=cik_or_ticker,
                persist=persist,
            )
        if artifact == "insider":
            return self._fetch_insider(
                cik_or_ticker=cik_or_ticker,
                start=start,
                end=end,
                persist=persist,
            )
        if artifact == "holdings":
            return self._fetch_holdings(
                cik_or_ticker=cik_or_ticker,
                start=start,
                end=end,
                persist=persist,
            )
        raise SecClientError(f"unknown artifact {artifact!r}")

    def capabilities(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain),
            "source_key": self.source_key,
            "forms": [
                "10-K",
                "10-Q",
                "8-K",
                "4",
                "13F-HR",
                "DEF 14A",
                "S-1",
                "N-PORT",
                "N-MFP",
            ],
            "artifacts": ["financials", "insider", "holdings"],
        }

    # ------------------------------------------------------------------
    # Artifact fetchers
    # ------------------------------------------------------------------

    def _fetch_financials(
        self,
        *,
        cik_or_ticker: str | int,
        persist: bool,
    ) -> ObservationsResult:
        company = self.client.company(cik_or_ticker)
        try:
            financials = company.get_financials()
        except Exception as exc:
            logger.info("edgar: get_financials failed for %s: %s", cik_or_ticker, exc)
            return ObservationsResult(data=pd.DataFrame())

        frames: list[pd.DataFrame] = []
        for statement in ("balance_sheet", "income_statement", "cash_flow"):
            df = standardize_financials(financials, statement=statement)
            if not df.empty:
                frames.append(df)
        if not frames:
            return ObservationsResult(data=pd.DataFrame())

        tidy = pd.concat(frames, ignore_index=True)
        cik = self._cik_from_company(company)
        ticker = self._ticker_from_company(company)
        tidy["cik"] = cik
        tidy["ticker"] = ticker

        lineage: dict[str, Any] = {}
        if persist:
            path = self._write_financials(cik or str(cik_or_ticker), tidy)
            lineage = self._register_lineage(
                name=f"sec.{cik or cik_or_ticker}.financials",
                domain=str(DataDomain.FILINGS_XBRL),
                df=tidy.rename(columns={"period": "timestamp"}),
                storage_uri=str(path),
                frequency="quarterly",
                meta={"artifact": "financials", "cik": cik, "ticker": ticker},
            )
            version_id = lineage.get("dataset_version_id")
            if version_id:
                register_data_links(
                    dataset_version_id=version_id,
                    source_name=self.source_key,
                    entity_rows=[
                        {
                            "entity_kind": "instrument",
                            "entity_id": ticker or cik or str(cik_or_ticker),
                            "instrument_vt_symbol": f"{ticker}.NASDAQ" if ticker else None,
                            "row_count": int(len(tidy)),
                            "meta": {"artifact": "financials"},
                        }
                    ],
                )
        return ObservationsResult(data=tidy, lineage=lineage)

    def _fetch_insider(
        self,
        *,
        cik_or_ticker: str | int,
        start: str | None,
        end: str | None,
        persist: bool,
    ) -> ObservationsResult:
        filings = self.client.get_filings(
            cik_or_ticker=cik_or_ticker,
            form="4",
            start=start,
            end=end,
            limit=200,
        )
        rows: list[pd.DataFrame] = []
        for filing in _iter_filings(filings):
            try:
                obj = filing.obj()
            except Exception:
                continue
            df = insider_transactions(obj)
            if not df.empty:
                df["accession_no"] = getattr(filing, "accession_number", None) or getattr(
                    filing, "accession_no", None
                )
                rows.append(df)
        if not rows:
            return ObservationsResult(data=pd.DataFrame())
        tidy = pd.concat(rows, ignore_index=True)

        lineage: dict[str, Any] = {}
        if persist:
            cik = str(cik_or_ticker)
            path = self._write_artifact(cik, "insider", tidy)
            lineage = self._register_lineage(
                name=f"sec.{cik}.insider",
                domain=str(DataDomain.FILINGS_INSIDER),
                df=tidy,
                storage_uri=str(path),
                frequency=None,
                meta={"artifact": "insider", "cik": cik},
            )
        return ObservationsResult(data=tidy, lineage=lineage)

    def _fetch_holdings(
        self,
        *,
        cik_or_ticker: str | int,
        start: str | None,
        end: str | None,
        persist: bool,
    ) -> ObservationsResult:
        filings = self.client.get_filings(
            cik_or_ticker=cik_or_ticker,
            form=["13F-HR", "13F-HR/A"],
            start=start,
            end=end,
            limit=50,
        )
        rows: list[pd.DataFrame] = []
        for filing in _iter_filings(filings):
            try:
                obj = filing.obj()
            except Exception:
                continue
            df = fund_holdings(obj)
            if not df.empty:
                df["accession_no"] = getattr(filing, "accession_number", None) or getattr(
                    filing, "accession_no", None
                )
                rows.append(df)
        if not rows:
            return ObservationsResult(data=pd.DataFrame())
        tidy = pd.concat(rows, ignore_index=True)

        lineage: dict[str, Any] = {}
        if persist:
            cik = str(cik_or_ticker)
            path = self._write_artifact(cik, "holdings", tidy)
            lineage = self._register_lineage(
                name=f"sec.{cik}.holdings",
                domain=str(DataDomain.FILINGS_OWNERSHIP),
                df=tidy,
                storage_uri=str(path),
                frequency=None,
                meta={"artifact": "holdings", "cik": cik},
            )
        return ObservationsResult(data=tidy, lineage=lineage)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_financials(self, cik: str, df: pd.DataFrame) -> Path:
        root = self.parquet_root / "financials" / _safe(cik)
        root.mkdir(parents=True, exist_ok=True)
        path = root / "financials.parquet"
        df.to_parquet(path, index=False)
        return path

    def _write_artifact(self, cik: str, artifact: str, df: pd.DataFrame) -> Path:
        root = self.parquet_root / artifact / _safe(cik)
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{artifact}.parquet"
        df.to_parquet(path, index=False)
        return path

    def _register_lineage(
        self,
        *,
        name: str,
        domain: str,
        df: pd.DataFrame,
        storage_uri: str,
        frequency: str | None,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        lineage_df = df.copy()
        if "timestamp" not in lineage_df.columns:
            lineage_df["timestamp"] = datetime.utcnow()
        if "vt_symbol" not in lineage_df.columns:
            ticker = meta.get("ticker") or meta.get("cik") or "SEC"
            lineage_df["vt_symbol"] = f"SEC:{ticker}"
        try:
            return register_dataset_version(
                name=name,
                provider="sec_edgar",
                domain=domain,
                df=lineage_df,
                storage_uri=storage_uri,
                frequency=frequency,
                meta=meta,
                file_count=1,
            )
        except Exception:
            logger.debug("sec lineage registration failed", exc_info=True)
            return {}

    def _filings_to_rows(self, filings: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for filing in _iter_filings(filings):
            row = {
                "cik": str(getattr(filing, "cik", "") or ""),
                "accession_no": str(
                    getattr(filing, "accession_number", None)
                    or getattr(filing, "accession_no", "")
                    or ""
                ),
                "form": str(getattr(filing, "form", "") or ""),
                "filed_at": getattr(filing, "filing_date", None) or getattr(filing, "filed_at", None),
                "period_of_report": getattr(filing, "period_of_report", None),
                "primary_doc_url": getattr(filing, "primary_doc_url", None)
                or getattr(filing, "homepage_url", None),
                "primary_doc_type": getattr(filing, "primary_doc_type", None),
                "xbrl_available": bool(getattr(filing, "has_xbrl", False)),
                "items": list(getattr(filing, "items", []) or []),
                "ticker": getattr(filing, "ticker", None),
                "meta": {
                    "header": getattr(filing, "header", None).__repr__()
                    if getattr(filing, "header", None)
                    else None,
                },
            }
            if not row["accession_no"]:
                continue
            rows.append(row)
        return rows

    def _cik_from_company(self, company: Any) -> str | None:
        cik = getattr(company, "cik", None)
        if cik is None:
            return None
        return str(cik).zfill(10) if isinstance(cik, int) else str(cik)

    def _ticker_from_company(self, company: Any) -> str | None:
        ticker = getattr(company, "ticker", None) or getattr(company, "tickers", None)
        if isinstance(ticker, (list, tuple)) and ticker:
            return str(ticker[0])
        return str(ticker) if ticker else None


def _iter_filings(filings: Any):
    """Iterate over an ``edgar.Filings`` collection (or any iterable of filings)."""
    if filings is None:
        return
    try:
        yield from filings
    except TypeError:
        try:
            yield filings
        except Exception:
            return


def _safe(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(" ", "_")
