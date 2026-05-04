"""Data discovery + ingestion endpoints.

Additions in this refactor:

- ``GET  /data/indicators``          — enumerate indicators known to
  :class:`aqp.data.indicators_zoo.IndicatorZoo`, with default kwargs and
  human-readable descriptions.
- ``POST /data/indicators/preview``  — apply a list of indicator specs to a
  single symbol's bar slice and return the overlay columns. Powers the
  Indicator Builder UI.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from aqp.api.schemas import (
    ActiveDailyOhlcvIngestRequest,
    DataSearchRequest,
    DiscoverResponse,
    IBKRHistoricalFetchRequest,
    IBKRHistoricalIngestRequest,
    IngestRequest,
    TaskAccepted,
    UniverseSyncRequest,
)
from aqp.config import settings
from aqp.core.types import Symbol
from aqp.data.chroma_store import ChromaStore
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog, DatasetVersion, Instrument
from aqp.tasks.ingestion_tasks import (
    index_chroma,
    ingest_active_daily_ohlcv,
    ingest_ibkr_historical,
    ingest_yahoo,
    load_local_directory,
    sync_alpha_vantage_universe,
)

router = APIRouter(prefix="/data", tags=["data"])


class LoadLocalRequest(BaseModel):
    source_dir: str = Field(..., description="Absolute path on the host filesystem")
    format: str = Field(default="csv", description="csv | parquet")
    glob: str | None = None
    column_map: dict[str, str] | None = None
    tz: str | None = None
    overwrite: bool = False


class DatasetCatalogSummary(BaseModel):
    id: str
    name: str
    provider: str
    domain: str
    frequency: str | None = None
    storage_uri: str | None = None
    latest_version: int | None = None
    latest_dataset_hash: str | None = None
    latest_row_count: int | None = None
    updated_at: datetime


class DatasetVersionSummary(BaseModel):
    id: str
    catalog_id: str
    version: int
    status: str
    dataset_hash: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    row_count: int
    symbol_count: int
    created_at: datetime


@router.post("/ingest", response_model=TaskAccepted)
def ingest(req: IngestRequest) -> TaskAccepted:
    async_result = ingest_yahoo.delay(req.symbols, req.start, req.end, req.interval, req.source)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/ingest/active-daily-ohlcv", response_model=TaskAccepted)
def ingest_active_daily_ohlcv_route(req: ActiveDailyOhlcvIngestRequest) -> TaskAccepted:
    async_result = ingest_active_daily_ohlcv.delay(
        req.years,
        req.end,
        req.source,
        req.chunk_size,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/universe/sync", response_model=TaskAccepted)
def sync_universe(req: UniverseSyncRequest) -> TaskAccepted:
    async_result = sync_alpha_vantage_universe.delay(
        req.state,
        req.limit,
        req.include_otc,
        req.query,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/universe")
def list_universe(
    limit: int = 200,
    offset: int = 0,
    query: str | None = None,
    source: str | None = None,
    state: str = "active",
    include_otc: bool = False,
) -> dict[str, Any]:
    policy = str(source or settings.universe_provider or "managed_snapshot").strip().lower()
    q = (query or "").strip()
    cap = max(1, min(int(limit), 5000))
    start = max(0, int(offset))

    items: list[dict[str, Any]] = []
    if policy in {"alpha_vantage", "alpha_vantage_live", "live"}:
        try:
            from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

            svc = AlphaVantageUniverseService()
            raw = svc.fetch_snapshot(state=state)
            normalized = svc.normalize_snapshot(
                raw,
                include_otc=include_otc,
                query=q or None,
                limit=None,
            )
            total = int(len(normalized))
            page = normalized.iloc[start : start + cap]
            items = [
                {
                    "id": "",
                    "vt_symbol": row["vt_symbol"],
                    "ticker": row["ticker"],
                    "exchange": row["exchange"],
                    "asset_class": row["asset_class"],
                    "security_type": row["security_type"],
                    "sector": None,
                    "industry": None,
                    "currency": row.get("currency") or "USD",
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "updated_at": None,
                }
                for row in page.to_dict(orient="records")
            ]
            return _universe_response("alpha_vantage_live", items, total=total, offset=start, limit=cap)
        except Exception:
            items = []
    elif policy in {"lake", "parquet", "parquet_lake", "disk", "bars_lake"}:
        items, total = _list_parquet_lake_universe(limit=cap, offset=start, query=q or None)
        return _universe_response("parquet_lake", items, total=total, offset=start, limit=cap)
    elif policy in {"catalog", "data_catalog", "instrument", "instruments"}:
        items, total = _list_catalog_universe(limit=cap, offset=start, query=q or None)
        return _universe_response("catalog", items, total=total, offset=start, limit=cap)
    elif policy != "config":
        try:
            from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

            items = AlphaVantageUniverseService().list_snapshot(limit=cap, offset=start, query=q or None)
            total = _count_instruments(query=q or None)
        except Exception:
            items = []
            total = 0

    if not items:
        source = "config"
        tickers = [s.strip().upper() for s in settings.universe_list if s and s.strip()]
        if q:
            tickers = [ticker for ticker in tickers if q.upper() in ticker]
        total = len(tickers)
        tickers = tickers[start : start + cap]
        items = [
            {
                "id": "",
                "vt_symbol": Symbol.parse(ticker).vt_symbol,
                "ticker": ticker,
                "exchange": Symbol.parse(ticker).exchange.value,
                "asset_class": "equity",
                "security_type": "equity",
                "sector": None,
                "industry": None,
                "currency": "USD",
                "updated_at": None,
            }
            for ticker in tickers
        ]
    else:
        source = "managed_snapshot"

    return _universe_response(source, items, total=total, offset=start, limit=cap)


def _universe_response(
    source: str,
    items: list[dict[str, Any]],
    *,
    total: int,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    next_offset = offset + len(items)
    return {
        "source": source,
        "count": len(items),
        "total": int(total),
        "offset": int(offset),
        "limit": int(limit),
        "next_offset": next_offset if next_offset < int(total) else None,
        "has_more": next_offset < int(total),
        "items": items,
    }


def _instrument_filter(stmt: Any, query: str | None) -> Any:
    q = (query or "").strip()
    if not q:
        return stmt
    needle = f"%{q}%"
    return stmt.where(
        (Instrument.ticker.ilike(needle))
        | (Instrument.vt_symbol.ilike(needle))
        | (Instrument.sector.ilike(needle))
        | (Instrument.industry.ilike(needle))
    )


def _count_instruments(query: str | None = None) -> int:
    with get_session() as session:
        stmt = _instrument_filter(select(func.count()).select_from(Instrument), query)
        return int(session.execute(stmt).scalar_one() or 0)


def _list_parquet_lake_universe(
    *,
    limit: int,
    offset: int = 0,
    query: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Symbols that have at least one row in the local Parquet ``bars`` lake."""
    provider = DuckDBHistoryProvider()
    frame = provider.describe_bars()
    if frame is None or frame.empty or "vt_symbol" not in frame.columns:
        return [], 0
    df = frame.sort_values("vt_symbol").reset_index(drop=True)
    if query:
        q = query.strip().upper()
        mask = df["vt_symbol"].astype(str).str.upper().str.contains(q, na=False)
        df = df.loc[mask].reset_index(drop=True)
    total = int(len(df))
    start = max(0, int(offset))
    cap = max(1, int(limit))
    page = df.iloc[start : start + cap]
    items: list[dict[str, Any]] = []
    for row in page.itertuples(index=False):
        vt = str(getattr(row, "vt_symbol", "") or "").strip().upper()
        if not vt:
            continue
        try:
            sym = Symbol.parse(vt)
        except Exception:
            continue
        items.append(
            {
                "id": "",
                "vt_symbol": sym.vt_symbol,
                "ticker": sym.ticker,
                "exchange": sym.exchange.value,
                "asset_class": sym.asset_class.value,
                "security_type": sym.security_type.value,
                "sector": None,
                "industry": None,
                "currency": "USD",
                "name": None,
                "status": None,
                "updated_at": None,
            }
        )
    return items, total


def _list_catalog_universe(
    *,
    limit: int,
    offset: int = 0,
    query: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    with get_session() as session:
        total = int(session.execute(_instrument_filter(select(func.count()).select_from(Instrument), query)).scalar_one() or 0)
        stmt = _instrument_filter(select(Instrument), query)
        rows = session.execute(
            stmt.order_by(Instrument.ticker.asc())
            .offset(max(0, int(offset)))
            .limit(max(1, int(limit)))
        ).scalars().all()
    return [
        {
            "id": row.id,
            "vt_symbol": row.vt_symbol,
            "ticker": row.ticker,
            "exchange": row.exchange,
            "asset_class": row.asset_class,
            "security_type": row.security_type,
            "sector": row.sector,
            "industry": row.industry,
            "currency": row.currency,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ], total


@router.get("/fabric/overview")
def fabric_overview() -> dict[str, Any]:
    """Aggregated view across the data fabric: sources, namespaces, instruments, links."""
    sources_summary: list[dict[str, Any]] = []
    try:
        from aqp.data.sources.registry import list_data_sources

        for source in list_data_sources():
            row = source if isinstance(source, dict) else dict(source)
            sources_summary.append(
                {
                    "name": row.get("name"),
                    "display_name": row.get("display_name"),
                    "kind": row.get("kind"),
                    "vendor": row.get("vendor"),
                    "enabled": bool(row.get("enabled")),
                    "domains": (row.get("capabilities") or {}).get("domains", []),
                }
            )
    except Exception:
        pass

    namespaces: list[str] = []
    table_count = 0
    try:
        from aqp.data import iceberg_catalog as ic

        namespaces = ic.list_namespaces()
        for ns in namespaces:
            table_count += len(ic.list_tables(ns))
    except Exception:
        pass

    instrument_count = 0
    identifier_link_count = 0
    catalog_summary: list[dict[str, Any]] = []
    try:
        from sqlalchemy import func as sa_func

        from aqp.persistence.models import IdentifierLink

        with get_session() as session:
            instrument_count = int(
                session.execute(select(sa_func.count()).select_from(Instrument)).scalar_one() or 0
            )
            identifier_link_count = int(
                session.execute(select(sa_func.count()).select_from(IdentifierLink)).scalar_one() or 0
            )
            rows = session.execute(
                select(DatasetCatalog).order_by(desc(DatasetCatalog.updated_at)).limit(50)
            ).scalars().all()
            for row in rows:
                catalog_summary.append(
                    {
                        "name": row.name,
                        "provider": row.provider,
                        "domain": row.domain,
                        "iceberg_identifier": row.iceberg_identifier,
                        "load_mode": row.load_mode,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                )
    except Exception:
        pass

    alpha_vantage_endpoints: list[dict[str, Any]] = []
    try:
        from aqp.data.sources.alpha_vantage.catalog import lake_supported_functions

        for fn in lake_supported_functions():
            entry = fn.to_dict()
            entry["last_refreshed_at"] = None
            for catalog_row in catalog_summary:
                if catalog_row.get("iceberg_identifier") == entry.get("iceberg_identifier"):
                    entry["last_refreshed_at"] = catalog_row.get("updated_at")
                    break
            alpha_vantage_endpoints.append(entry)
    except Exception:
        pass

    return {
        "sources": sources_summary,
        "namespaces": namespaces,
        "namespace_count": len(namespaces),
        "table_count": table_count,
        "instrument_count": instrument_count,
        "identifier_link_count": identifier_link_count,
        "catalog_recent": catalog_summary,
        "alpha_vantage_endpoints": alpha_vantage_endpoints,
    }


@router.get("/securities/{vt_symbol}/coverage")
def security_coverage(vt_symbol: str) -> dict[str, Any]:
    """Return every Iceberg-backed dataset that contains rows for ``vt_symbol``.

    Joins :class:`DataLink` to :class:`DatasetVersion` and :class:`DatasetCatalog`
    so the data fabric UI can answer "what data do we have about AAPL.NASDAQ"
    without scanning parquet files.
    """
    from aqp.persistence.models import DataLink

    vt = (vt_symbol or "").strip()
    if not vt:
        raise HTTPException(400, "vt_symbol is required")

    with get_session() as session:
        instrument = session.execute(
            select(Instrument).where(Instrument.vt_symbol == vt).limit(1)
        ).scalar_one_or_none()
        if instrument is None:
            return {
                "vt_symbol": vt,
                "instrument_id": None,
                "datasets": [],
                "identifier_links": [],
            }

        dataset_rows = (
            session.execute(
                select(DataLink, DatasetVersion, DatasetCatalog)
                .join(DatasetVersion, DataLink.dataset_version_id == DatasetVersion.id, isouter=True)
                .join(DatasetCatalog, DatasetVersion.catalog_id == DatasetCatalog.id, isouter=True)
                .where(DataLink.instrument_id == instrument.id)
            )
            .all()
        )

        by_catalog: dict[str, dict[str, Any]] = {}
        for link, version, catalog in dataset_rows:
            if catalog is None:
                continue
            slot = by_catalog.setdefault(
                catalog.id,
                {
                    "catalog_id": catalog.id,
                    "iceberg_identifier": catalog.iceberg_identifier,
                    "name": catalog.name,
                    "provider": catalog.provider,
                    "domain": catalog.domain,
                    "row_count": 0,
                    "coverage_start": None,
                    "coverage_end": None,
                    "latest_version": version.version if version else None,
                },
            )
            slot["row_count"] = int(slot["row_count"]) + int(getattr(link, "row_count", 0) or 0)
            cs = link.coverage_start
            ce = link.coverage_end
            if cs and (slot["coverage_start"] is None or cs.isoformat() < slot["coverage_start"]):
                slot["coverage_start"] = cs.isoformat()
            if ce and (slot["coverage_end"] is None or ce.isoformat() > slot["coverage_end"]):
                slot["coverage_end"] = ce.isoformat()
            if version and (slot["latest_version"] is None or version.version > slot["latest_version"]):
                slot["latest_version"] = version.version

        datasets = sorted(by_catalog.values(), key=lambda row: row.get("name") or "")

        try:
            from aqp.data.sources.resolvers.identifiers import IdentifierResolver

            identifiers = IdentifierResolver().instrument_identifiers(instrument.id)
        except Exception:
            identifiers = []

        return {
            "vt_symbol": instrument.vt_symbol,
            "instrument_id": instrument.id,
            "ticker": instrument.ticker,
            "exchange": instrument.exchange,
            "asset_class": instrument.asset_class,
            "datasets": datasets,
            "identifier_links": [
                {
                    "scheme": entry.get("scheme"),
                    "value": entry.get("value"),
                    "source_id": entry.get("source_id"),
                    "confidence": entry.get("confidence"),
                }
                for entry in identifiers
            ],
        }


@router.post("/load", response_model=TaskAccepted)
def load_local(req: LoadLocalRequest) -> TaskAccepted:
    async_result = load_local_directory.delay(
        req.source_dir,
        req.format,
        req.glob,
        req.column_map,
        req.tz,
        req.overwrite,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/index", response_model=TaskAccepted)
def index() -> TaskAccepted:
    async_result = index_chroma.delay()
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/search", response_model=DiscoverResponse)
def search(req: DataSearchRequest) -> DiscoverResponse:
    try:
        hits = ChromaStore().search_datasets(req.query, k=req.k)
    except Exception as e:
        return DiscoverResponse(results=[{"error": str(e)}])
    return DiscoverResponse(results=hits)


@router.get("/describe")
def describe() -> list[dict]:
    df = DuckDBHistoryProvider().describe_bars()
    if df.empty:
        return []
    df["first_bar"] = df["first_bar"].astype(str)
    df["last_bar"] = df["last_bar"].astype(str)
    return df.to_dict(orient="records")


@router.get("/catalog", response_model=list[DatasetCatalogSummary])
def list_catalog(limit: int = 100) -> list[DatasetCatalogSummary]:
    with get_session() as session:
        rows = session.execute(
            select(DatasetCatalog).order_by(desc(DatasetCatalog.updated_at)).limit(limit)
        ).scalars().all()
        out: list[DatasetCatalogSummary] = []
        for row in rows:
            latest = session.execute(
                select(DatasetVersion)
                .where(DatasetVersion.catalog_id == row.id)
                .order_by(desc(DatasetVersion.version))
                .limit(1)
            ).scalar_one_or_none()
            out.append(
                DatasetCatalogSummary(
                    id=row.id,
                    name=row.name,
                    provider=row.provider,
                    domain=row.domain,
                    frequency=row.frequency,
                    storage_uri=row.storage_uri,
                    latest_version=latest.version if latest else None,
                    latest_dataset_hash=latest.dataset_hash if latest else None,
                    latest_row_count=latest.row_count if latest else None,
                    updated_at=row.updated_at,
                )
            )
        return out


@router.get("/catalog/{catalog_id}/versions", response_model=list[DatasetVersionSummary])
def list_catalog_versions(catalog_id: str, limit: int = 50) -> list[DatasetVersionSummary]:
    with get_session() as session:
        rows = session.execute(
            select(DatasetVersion)
            .where(DatasetVersion.catalog_id == catalog_id)
            .order_by(desc(DatasetVersion.version))
            .limit(limit)
        ).scalars().all()
        return [
            DatasetVersionSummary(
                id=row.id,
                catalog_id=row.catalog_id,
                version=row.version,
                status=row.status,
                dataset_hash=row.dataset_hash,
                start_time=row.start_time,
                end_time=row.end_time,
                row_count=row.row_count,
                symbol_count=row.symbol_count,
                created_at=row.created_at,
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Data-browser surface: per-symbol bar slice + gap / stats report
# ---------------------------------------------------------------------------


@router.post("/ibkr/historical/fetch")
async def fetch_ibkr_historical(req: IBKRHistoricalFetchRequest) -> dict[str, Any]:
    from aqp.data import ibkr_historical as ibkr_mod

    service = ibkr_mod.IBKRHistoricalService()
    try:
        df = await service.fetch_bars(
            vt_symbol=req.vt_symbol,
            start=req.start,
            end=req.end,
            end_date_time=req.end_date_time,
            duration_str=req.duration_str,
            bar_size=req.bar_size,
            what_to_show=req.what_to_show,
            use_rth=req.use_rth,
            exchange=req.exchange,
            currency=req.currency,
        )
    except ibkr_mod.IBKRHistoricalValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"detail": str(exc), "code": "validation", "hint": "Check bar_size, what_to_show and date range."},
        ) from exc
    except ibkr_mod.IBKRHistoricalDependencyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"detail": str(exc), "code": "dependency_missing", "hint": "pip install aqp[ibkr]"},
        ) from exc
    except ibkr_mod.IBKRHistoricalPacingError as exc:
        raise HTTPException(
            status_code=429,
            detail={"detail": str(exc), "code": "pacing", "hint": "Wait a few seconds and retry."},
        ) from exc
    except ibkr_mod.IBKRHistoricalUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": str(exc),
                "code": "ibkr_unavailable",
                "hint": "Start TWS / IB Gateway and enable API socket access.",
            },
        ) from exc
    except ibkr_mod.IBKRHistoricalTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "detail": str(exc),
                "code": "timeout",
                "hint": "IBKR timed out — try a smaller range or retry in a moment.",
            },
        ) from exc
    except ibkr_mod.IBKRHistoricalError as exc:
        raise HTTPException(
            status_code=502,
            detail={"detail": str(exc), "code": "provider_error", "hint": "Inspect TWS logs for details."},
        ) from exc

    if df.empty:
        return {
            "source": "ibkr",
            "vt_symbol": req.vt_symbol,
            "count": 0,
            "bars": [],
            "first_ts": None,
            "last_ts": None,
            "what_to_show": req.what_to_show.upper(),
            "bar_size": req.bar_size,
            "use_rth": bool(req.use_rth),
        }
    df = df.sort_values("timestamp").tail(req.rows).copy()
    first_ts = str(df["timestamp"].iloc[0])
    last_ts = str(df["timestamp"].iloc[-1])
    df["timestamp"] = df["timestamp"].astype(str)
    return {
        "source": "ibkr",
        "vt_symbol": str(df["vt_symbol"].iloc[0]),
        "count": int(len(df)),
        "bars": df.to_dict(orient="records"),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "what_to_show": req.what_to_show.upper(),
        "bar_size": req.bar_size,
        "use_rth": bool(req.use_rth),
    }


@router.post("/ibkr/historical/ingest", response_model=TaskAccepted)
def ingest_ibkr_history(req: IBKRHistoricalIngestRequest) -> TaskAccepted:
    async_result = ingest_ibkr_historical.delay(req.model_dump())
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/ibkr/historical/availability")
def ibkr_historical_availability(refresh: bool = False) -> dict[str, Any]:
    """Lightweight TWS / IB Gateway reachability probe used by the UI."""
    from aqp.config import settings as cfg
    from aqp.data.ibkr_historical import IBKRHistoricalService

    ok, message = IBKRHistoricalService.is_available(use_cache=not refresh)
    return {
        "ok": bool(ok),
        "message": message,
        "host": cfg.ibkr_host,
        "port": cfg.ibkr_port,
    }


@router.get("/{vt_symbol}/bars")
def get_symbol_bars(
    vt_symbol: str,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
    normalization: str = "adjusted",
    limit: int = 5000,
) -> dict:
    import datetime as _dt

    from aqp.core.types import DataNormalizationMode, Symbol

    sym = Symbol.parse(vt_symbol)
    try:
        start_dt = _dt.datetime.fromisoformat(start) if start else _dt.datetime(2000, 1, 1)
    except ValueError:
        start_dt = _dt.datetime(2000, 1, 1)
    try:
        end_dt = _dt.datetime.fromisoformat(end) if end else _dt.datetime.utcnow()
    except ValueError:
        end_dt = _dt.datetime.utcnow()
    try:
        mode = DataNormalizationMode(normalization)
    except ValueError:
        mode = DataNormalizationMode.ADJUSTED
    provider = DuckDBHistoryProvider()
    df = provider.get_bars_normalized(
        [sym],
        start_dt,
        end_dt,
        interval=interval,
        normalization=mode,
    )
    if df.empty:
        return {"vt_symbol": vt_symbol, "bars": [], "count": 0}
    df = df.sort_values("timestamp").tail(limit)
    df["timestamp"] = df["timestamp"].astype(str)
    return {
        "vt_symbol": vt_symbol,
        "count": int(len(df)),
        "bars": df.to_dict(orient="records"),
    }


@router.get("/{vt_symbol}/stats")
def get_symbol_stats(
    vt_symbol: str,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
) -> dict:
    import datetime as _dt

    provider = DuckDBHistoryProvider()
    try:
        start_dt = _dt.datetime.fromisoformat(start) if start else _dt.datetime(2000, 1, 1)
    except ValueError:
        start_dt = _dt.datetime(2000, 1, 1)
    try:
        end_dt = _dt.datetime.fromisoformat(end) if end else _dt.datetime.utcnow()
    except ValueError:
        end_dt = _dt.datetime.utcnow()
    return provider.gap_report(vt_symbol, start_dt, end_dt, interval=interval)


# ---------------------------------------------------------------------------
# Indicator introspection + preview
# ---------------------------------------------------------------------------


class IndicatorPreviewRequest(BaseModel):
    vt_symbol: str = Field(..., description="e.g. AAPL.NASDAQ")
    indicators: list[str] = Field(
        default_factory=lambda: ["SMA:20", "RSI:14"],
        description='e.g. ["SMA:20", "EMA:26", "RSI:14", "MACD"]',
    )
    start: str | None = None
    end: str | None = None
    interval: str = "1d"
    rows: int = Field(default=400, ge=10, le=5000)


class IndicatorDescriptor(BaseModel):
    name: str
    category: str = "other"
    default_period: int | None = None
    description: str = ""


_INDICATOR_META: dict[str, tuple[str, int | None, str]] = {
    # Trend
    "SMA": ("trend", 20, "Simple moving average."),
    "EMA": ("trend", 12, "Exponential moving average."),
    "HMA": ("trend", 20, "Hull moving average."),
    "KAMA": ("trend", 10, "Kaufman adaptive MA."),
    # Momentum / oscillators
    "RSI": ("oscillator", 14, "Relative Strength Index."),
    "MACD": ("oscillator", None, "MACD (12/26/9) with signal + histogram."),
    "Stochastic": ("oscillator", 14, "Fast stochastic %K / %D."),
    "CCI": ("oscillator", 20, "Commodity Channel Index."),
    "WilliamsR": ("oscillator", 14, "Williams %R."),
    "MFI": ("oscillator", 14, "Money Flow Index."),
    "UO": ("oscillator", None, "Ultimate Oscillator."),
    "Aroon": ("oscillator", 14, "Aroon oscillator."),
    "TRIX": ("oscillator", 15, "Triple exponential smoothed momentum."),
    # Volatility / bands
    "BBands": ("bands", 20, "Bollinger Bands."),
    "ATR": ("volatility", 14, "Average True Range."),
    "Keltner": ("bands", 20, "Keltner Channels."),
    "Donchian": ("bands", 20, "Donchian Channel."),
    "PSAR": ("bands", None, "Parabolic SAR."),
    "ADX": ("trend", 14, "Average Directional Index."),
    # Volume
    "ChaikinOsc": ("volume", None, "Chaikin oscillator."),
    "OBV": ("volume", None, "On-Balance Volume."),
    "VWAP": ("volume", None, "Volume-weighted average price."),
    # Statistical
    "Z": ("statistical", 20, "Rolling z-score."),
    "LogReturn": ("statistical", 1, "Log return over n bars."),
    "ROC": ("statistical", 12, "Rate of change."),
    "StdDev": ("statistical", 20, "Rolling standard deviation."),
    "Ichimoku": ("trend", None, "Ichimoku cloud (tenkan/kijun/span)."),
}


@router.get("/indicators", response_model=list[IndicatorDescriptor])
def list_indicators() -> list[IndicatorDescriptor]:
    """Enumerate indicators known to :class:`IndicatorZoo`."""
    from aqp.data.indicators_zoo import IndicatorZoo

    zoo = IndicatorZoo()
    out: list[IndicatorDescriptor] = []
    for name in zoo.known():
        category, default_period, description = _INDICATOR_META.get(
            name, ("other", None, "No description available.")
        )
        out.append(
            IndicatorDescriptor(
                name=name,
                category=category,
                default_period=default_period,
                description=description,
            )
        )
    return out


@router.get("/indicators/catalog")
def list_indicator_catalog() -> dict[str, Any]:
    """Return the full TA-Lib taxonomy with engine availability per entry.

    Drives the Data Browser's indicator catalog. Always returns metadata
    even when no compute engine is installed, so the UI can still render
    the full taxonomy.
    """
    from aqp.data import talib_catalog

    return talib_catalog.catalog()


@router.post("/indicators/preview")
def indicator_preview(req: IndicatorPreviewRequest) -> dict[str, Any]:
    """Apply a list of indicator specs to one symbol's bar slice.

    Returns the last ``rows`` rows with one column per indicator overlay.
    Safe: read-only, no side effects.
    """
    import datetime as _dt

    from aqp.core.types import DataNormalizationMode, Symbol
    from aqp.data.indicators_zoo import IndicatorZoo

    if not req.indicators:
        raise HTTPException(400, "indicators must be a non-empty list")

    sym = Symbol.parse(req.vt_symbol) if "." in req.vt_symbol else Symbol(ticker=req.vt_symbol)
    try:
        start_dt = _dt.datetime.fromisoformat(req.start) if req.start else _dt.datetime(2000, 1, 1)
    except ValueError:
        start_dt = _dt.datetime(2000, 1, 1)
    try:
        end_dt = _dt.datetime.fromisoformat(req.end) if req.end else _dt.datetime.utcnow()
    except ValueError:
        end_dt = _dt.datetime.utcnow()

    provider = DuckDBHistoryProvider()
    bars = provider.get_bars_normalized(
        [sym],
        start_dt,
        end_dt,
        interval=req.interval,
        normalization=DataNormalizationMode.ADJUSTED,
    )
    if bars is None or bars.empty:
        return {"vt_symbol": req.vt_symbol, "bars": [], "count": 0, "overlays": []}

    try:
        enriched = IndicatorZoo().transform(bars, indicators=req.indicators)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"indicator computation failed: {exc}") from exc

    overlays = [c for c in enriched.columns if c not in bars.columns]
    tail = enriched.sort_values("timestamp").tail(req.rows).copy()
    tail["timestamp"] = tail["timestamp"].astype(str)
    return {
        "vt_symbol": req.vt_symbol,
        "count": int(len(tail)),
        "overlays": overlays,
        "bars": tail.to_dict(orient="records"),
    }
