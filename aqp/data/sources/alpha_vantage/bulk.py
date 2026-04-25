"""Bulk Alpha Vantage loaders for AQP-managed storage."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from aqp.config import settings
from aqp.data.catalog import register_dataset_version
from aqp.data.sources.alpha_vantage import AlphaVantageClient


@dataclass
class BulkLoadResult:
    category: str
    uploaded_objects: int = 0
    skipped_symbols: int = 0
    errors: int = 0
    keys: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)
    lineage: dict[str, Any] = field(default_factory=dict)


def run_bulk_load(
    *,
    category: str,
    symbols: Sequence[str] = (),
    date_range: Mapping[str, str] | None = None,
    extra_params: Mapping[str, Any] | None = None,
    target_bucket: str | None = None,
) -> BulkLoadResult:
    """Fetch a batch of Alpha Vantage payloads and persist raw JSON/CSV locally."""
    started = time.perf_counter()
    category_slug = _slug(category)
    target_root = Path(target_bucket or settings.data_dir / "alpha_vantage" / "raw")
    target_root.mkdir(parents=True, exist_ok=True)
    result = BulkLoadResult(category=category_slug)
    client = AlphaVantageClient()
    extras = dict(extra_params or {})
    rows: list[dict[str, Any]] = []
    try:
        if category_slug in {"universe", "listing"}:
            payload = client.listing_status(state=str(extras.get("state") or "active"))
            key = _write_frame(target_root, category_slug, "listing_status", payload)
            result.keys.append(key)
            result.uploaded_objects += 1
            rows.append({"timestamp": _now(), "vt_symbol": "UNIVERSE.ALPHA_VANTAGE", "key": key})
        else:
            for symbol in _clean_symbols(symbols):
                try:
                    payload = _fetch_category(client, category_slug, symbol, extras, dict(date_range or {}))
                    key = _write_payload(target_root, category_slug, symbol, payload)
                    result.keys.append(key)
                    result.uploaded_objects += 1
                    rows.append({"timestamp": _now(), "vt_symbol": f"{symbol}.NASDAQ", "key": key})
                except Exception as exc:  # noqa: BLE001
                    result.errors += 1
                    result.notes.append(f"{symbol}: {exc}")
        if rows:
            df = pd.DataFrame(rows)
            result.lineage = register_dataset_version(
                name=f"alpha_vantage_{category_slug}",
                provider="alpha_vantage",
                domain=_domain_for(category_slug),
                df=df,
                storage_uri=str(target_root),
                frequency=str(extras.get("interval") or extras.get("function") or category_slug),
                tags=["alpha_vantage", category_slug],
                meta={"keys": result.keys[:200]},
                file_count=len(result.keys),
            )
    finally:
        client.close()
        result.duration_seconds = time.perf_counter() - started
    return result


def _fetch_category(
    client: AlphaVantageClient,
    category: str,
    symbol: str,
    extras: Mapping[str, Any],
    date_range: Mapping[str, str],
) -> Any:
    if category in {"timeseries", "bars"}:
        function = str(extras.get("function") or "daily")
        if function == "intraday":
            return client.timeseries.intraday(
                symbol,
                interval=str(extras.get("interval") or "5min"),
                outputsize=str(extras.get("outputsize") or "compact"),
            ).model_dump()
        if function == "daily_adjusted":
            return client.timeseries.daily_adjusted(symbol, outputsize=str(extras.get("outputsize") or "full")).model_dump()
        return client.timeseries.daily(symbol, outputsize=str(extras.get("outputsize") or "full")).model_dump()
    if category in {"fundamentals", "overview"}:
        return client.fundamentals.overview(symbol).model_dump()
    if category == "news":
        return client.intelligence.news(tickers=symbol, limit=int(extras.get("limit") or 50)).model_dump()
    if category == "earnings":
        return client.fundamentals.earnings(symbol).model_dump()
    if category == "technicals":
        indicator = str(extras.get("indicator") or "SMA")
        return client.technicals.get(
            indicator,
            symbol,
            interval=str(extras.get("interval") or "daily"),
            time_period=extras.get("time_period") or 20,
            series_type=str(extras.get("series_type") or "close"),
        ).model_dump()
    if category == "options":
        date = date_range.get("end") or extras.get("date")
        return client._json(function="HISTORICAL_OPTIONS", symbol=symbol, date=date)
    raise ValueError(f"Unsupported Alpha Vantage bulk category: {category}")


def _write_payload(root: Path, category: str, symbol: str, payload: Any) -> str:
    path = root / category / symbol.upper() / f"{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    return str(path)


def _write_frame(root: Path, category: str, name: str, frame: pd.DataFrame) -> str:
    path = root / category / f"{name}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return str(path)


def _clean_symbols(symbols: Sequence[str]) -> list[str]:
    return [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]


def _slug(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_for(category: str) -> str:
    return {
        "timeseries": "market.bars",
        "bars": "market.bars",
        "fundamentals": "fundamentals.overview",
        "overview": "fundamentals.overview",
        "news": "news.sentiment",
        "earnings": "fundamentals.earnings",
        "technicals": "market.indicators",
        "options": "derivatives.options",
        "universe": "reference.instruments",
        "listing": "reference.instruments",
    }.get(category, f"alpha_vantage.{category}")


__all__ = ["BulkLoadResult", "run_bulk_load"]
