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
from sqlalchemy import desc, select

from aqp.api.schemas import (
    DataSearchRequest,
    DiscoverResponse,
    IBKRHistoricalFetchRequest,
    IBKRHistoricalIngestRequest,
    IngestRequest,
    TaskAccepted,
    UniverseSyncRequest,
)
from aqp.config import settings
from aqp.data.chroma_store import ChromaStore
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog, DatasetVersion
from aqp.tasks.ingestion_tasks import (
    index_chroma,
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
    query: str | None = None,
) -> dict[str, Any]:
    policy = str(settings.universe_provider or "managed_snapshot").strip().lower()
    q = (query or "").strip()

    items: list[dict[str, Any]] = []
    if policy != "config":
        try:
            from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

            items = AlphaVantageUniverseService().list_snapshot(limit=limit, query=q or None)
        except Exception:
            items = []

    if not items:
        source = "config"
        tickers = [s.strip().upper() for s in settings.universe_list if s and s.strip()]
        if q:
            tickers = [ticker for ticker in tickers if q.upper() in ticker]
        tickers = tickers[: max(1, int(limit))]
        items = [
            {
                "id": "",
                "vt_symbol": f"{ticker}.NASDAQ",
                "ticker": ticker,
                "exchange": "NASDAQ",
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

    return {
        "source": source,
        "count": len(items),
        "items": items,
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
