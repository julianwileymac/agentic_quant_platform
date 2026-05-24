"""Bulk-load helpers for the Alpha Vantage pipeline CLI.

Implements the ``alphavantage-bulk`` subcommand invoked by Argo WorkflowTemplates.
For each category:

* builds an :class:`AlphaVantageClient` using the same token resolution as the
  backend / streaming producer;
* iterates the supplied symbol list (and optional date range);
* writes the raw JSON payload to MinIO at
  ``s3://<bucket>/<category>/<symbol>/<slice>.json``;
* optionally upserts a summary row into Redis-OM via the new AV model family.

Degrades gracefully when the optional AV client, boto3, or redis-om packages
are missing so the pipeline image can be minimal.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from .config import PipelineConfig

logger = logging.getLogger(__name__)


try:  # pragma: no cover
    from alphavantage_client import AlphaVantageClient

    _CLIENT_AVAILABLE = True
except ImportError as exc:  # pragma: no cover
    AlphaVantageClient = None  # type: ignore[assignment]
    _CLIENT_AVAILABLE = False
    _CLIENT_IMPORT_ERROR = str(exc)


try:  # pragma: no cover
    import boto3
    from botocore.config import Config as _BotoConfig

    _BOTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]
    _BotoConfig = None  # type: ignore[assignment]
    _BOTO_AVAILABLE = False


@dataclass
class BulkLoadResult:
    category: str
    uploaded_objects: int = 0
    skipped_symbols: int = 0
    errors: int = 0
    keys: List[str] = field(default_factory=list)
    redis_rows: int = 0
    duration_seconds: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class MinioTarget:
    bucket: str
    prefix: str = ""


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------


def _minio_client(config: PipelineConfig) -> Any:
    if not _BOTO_AVAILABLE:
        raise RuntimeError("boto3 is required for AV bulk loads")
    endpoint = os.environ.get("PIPELINE_MINIO_ENDPOINT") or config.minio_endpoint
    access_key = os.environ.get("PIPELINE_MINIO_ACCESS_KEY") or config.minio_access_key
    secret_key = os.environ.get("PIPELINE_MINIO_SECRET_KEY") or config.minio_secret_key
    region = os.environ.get("PIPELINE_MINIO_REGION") or config.minio_region or "us-east-1"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=_BotoConfig(signature_version="s3v4"),
    )


def _upload_json(client: Any, target: MinioTarget, key: str, payload: Any) -> str:
    body = json.dumps(payload, default=str).encode("utf-8")
    object_key = f"{target.prefix.rstrip('/')}/{key.lstrip('/')}" if target.prefix else key
    client.put_object(
        Bucket=target.bucket,
        Key=object_key,
        Body=io.BytesIO(body),
        ContentType="application/json",
    )
    return object_key


def _upload_csv(client: Any, target: MinioTarget, key: str, payload: str) -> str:
    object_key = f"{target.prefix.rstrip('/')}/{key.lstrip('/')}" if target.prefix else key
    client.put_object(
        Bucket=target.bucket,
        Key=object_key,
        Body=payload.encode("utf-8"),
        ContentType="text/csv",
    )
    return object_key


# ---------------------------------------------------------------------------
# Public bulk-load entrypoint
# ---------------------------------------------------------------------------


def run_bulk_load(
    *,
    config: PipelineConfig,
    category: str,
    symbols: Sequence[str] = (),
    date_range: Optional[Mapping[str, str]] = None,
    extra_params: Optional[Mapping[str, Any]] = None,
    target_bucket: str = "av-raw",
    target_prefix: str = "",
    api_key_file: Optional[str] = None,
    api_key: Optional[str] = None,
    cache_backend: str = "memory",
) -> BulkLoadResult:
    """Fan out an AV bulk load for ``category`` over ``symbols``."""

    if not _CLIENT_AVAILABLE:
        raise RuntimeError(f"alphavantage_client is required: {_CLIENT_IMPORT_ERROR}")

    started = time.perf_counter()
    target = MinioTarget(bucket=target_bucket, prefix=target_prefix.strip("/"))
    client = AlphaVantageClient(
        api_key=api_key,
        api_key_file=api_key_file,
        cache_backend=cache_backend,
    )
    s3 = _minio_client(config)
    result = BulkLoadResult(category=category)
    extras = dict(extra_params or {})

    try:
        loader = _LOADERS.get(category.lower())
        if loader is None:
            raise ValueError(f"Unsupported AV bulk category: {category!r}")
        loader(
            client=client,
            s3=s3,
            target=target,
            symbols=list(symbols),
            date_range=dict(date_range or {}),
            extras=extras,
            result=result,
        )
    finally:
        client.close()
        result.duration_seconds = time.perf_counter() - started

    return result


# ---------------------------------------------------------------------------
# Category-specific loaders
# ---------------------------------------------------------------------------


def _load_timeseries(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    outputsize = str(extras.get("outputsize", "full"))
    function = str(extras.get("function", "daily"))
    slug = _slugify(function)
    ts = client.timeseries
    call_map = {
        "intraday": ts.intraday,
        "daily": ts.daily,
        "daily_adjusted": ts.daily_adjusted,
        "weekly": ts.weekly,
        "weekly_adjusted": ts.weekly_adjusted,
        "monthly": ts.monthly,
        "monthly_adjusted": ts.monthly_adjusted,
    }
    call = call_map.get(function)
    if call is None:
        raise ValueError(f"Unknown timeseries function {function!r}")

    for symbol in symbols:
        try:
            kwargs: dict[str, Any] = {}
            if function in {"daily", "daily_adjusted", "intraday"}:
                kwargs["outputsize"] = outputsize
            if function == "intraday":
                kwargs["interval"] = str(extras.get("interval", "5min"))
                if extras.get("month"):
                    kwargs["month"] = str(extras["month"])
            payload = call(symbol, **kwargs)
            key = f"timeseries/{slug}/{symbol}/{_today_slug()}.json"
            stored = _upload_json(s3, target, key, payload.model_dump(by_alias=False))
            result.keys.append(stored)
            result.uploaded_objects += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("timeseries load failed for %s: %s", symbol, exc)
            result.errors += 1


def _load_intraday_backfill(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    interval = str(extras.get("interval", "5min"))
    months = list(_iter_months(date_range.get("start"), date_range.get("end")))
    if not months:
        result.notes.append("no date_range provided; defaulting to the current month")
        months = [datetime.utcnow().strftime("%Y-%m")]
    for symbol in symbols:
        for month in months:
            try:
                payload = client.timeseries.intraday(
                    symbol,
                    interval=interval,
                    outputsize="full",
                    month=month,
                )
                key = f"intraday/{symbol}/{interval}/{month}.json"
                stored = _upload_json(s3, target, key, payload.model_dump(by_alias=False))
                result.keys.append(stored)
                result.uploaded_objects += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("intraday backfill failed %s %s: %s", symbol, month, exc)
                result.errors += 1


def _load_fundamentals(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    kinds = [k.strip() for k in str(extras.get("kinds", "overview,income,balance,cashflow,earnings")).split(",")]
    fn = client.fundamentals
    dispatch = {
        "overview": lambda s: fn.overview(s).model_dump(by_alias=False),
        "etf": lambda s: fn.etf_profile(s).model_dump(by_alias=False),
        "dividends": lambda s: [d.model_dump(by_alias=False) for d in fn.dividends(s)],
        "splits": lambda s: [sp.model_dump(by_alias=False) for sp in fn.splits(s)],
        "income": lambda s: _normalize_statements(fn.income_statement(s)),
        "balance": lambda s: _normalize_statements(fn.balance_sheet(s)),
        "cashflow": lambda s: _normalize_statements(fn.cash_flow(s)),
        "earnings": lambda s: _normalize_earnings(fn.earnings(s)),
        "estimates": lambda s: [e.model_dump(by_alias=False) for e in fn.earnings_estimates(s)],
        "shares": lambda s: [e.model_dump(by_alias=False) for e in fn.shares_outstanding(s)],
    }
    for symbol in symbols:
        for kind in kinds:
            if kind not in dispatch:
                continue
            try:
                data = dispatch[kind](symbol)
                key = f"fundamentals/{kind}/{symbol}/{_today_slug()}.json"
                stored = _upload_json(s3, target, key, data)
                result.keys.append(stored)
                result.uploaded_objects += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("fundamentals load failed %s %s: %s", symbol, kind, exc)
                result.errors += 1


def _load_universe(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    fn = client.fundamentals
    try:
        listing_csv = fn.listing_status(date=date_range.get("start"), state=extras.get("state"))
        stored = _upload_csv(s3, target, f"universe/listing/{_today_slug()}.csv", listing_csv)
        result.keys.append(stored)
        result.uploaded_objects += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("listing_status load failed: %s", exc)
        result.errors += 1
    try:
        ipo_csv = fn.ipo_calendar()
        stored = _upload_csv(s3, target, f"universe/ipo/{_today_slug()}.csv", ipo_csv)
        result.keys.append(stored)
        result.uploaded_objects += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("ipo_calendar load failed: %s", exc)
        result.errors += 1


def _load_news(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    tickers = list(symbols) or None
    topics = extras.get("topics")
    if isinstance(topics, str):
        topics = [t.strip() for t in topics.split(",") if t.strip()]
    try:
        payload = client.intelligence.news(
            tickers=tickers,
            topics=topics,
            time_from=date_range.get("start"),
            time_to=date_range.get("end"),
            limit=int(extras.get("limit", 1000)),
        )
        digest = hashlib.sha256(str(tickers).encode("utf-8")).hexdigest()[:8]
        key = f"news/{_today_slug()}/{digest}.json"
        stored = _upload_json(s3, target, key, payload.model_dump(by_alias=False))
        result.keys.append(stored)
        result.uploaded_objects += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("news load failed: %s", exc)
        result.errors += 1


def _load_earnings(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    fn = client.fundamentals
    for symbol in symbols:
        try:
            payload = fn.earnings(symbol)
            stored = _upload_json(
                s3, target,
                f"earnings/{symbol}/{_today_slug()}.json",
                payload.model_dump(by_alias=False),
            )
            result.keys.append(stored)
            result.uploaded_objects += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("earnings load failed %s: %s", symbol, exc)
            result.errors += 1


def _load_fx(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    for pair in symbols:
        try:
            frm, to = _split_pair(pair)
            series = client.forex.daily(from_symbol=frm, to_symbol=to, outputsize="full")
            stored = _upload_json(
                s3, target,
                f"fx/daily/{frm}-{to}/{_today_slug()}.json",
                series.model_dump(by_alias=False),
            )
            result.keys.append(stored)
            result.uploaded_objects += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("fx load failed %s: %s", pair, exc)
            result.errors += 1


def _load_crypto(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    market = str(extras.get("market", "USD"))
    for symbol in symbols:
        try:
            series = client.crypto.daily(symbol, market)
            stored = _upload_json(
                s3, target,
                f"crypto/daily/{symbol}-{market}/{_today_slug()}.json",
                series.model_dump(by_alias=False),
            )
            result.keys.append(stored)
            result.uploaded_objects += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("crypto load failed %s: %s", symbol, exc)
            result.errors += 1


def _load_commodities(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    interval = str(extras.get("interval", "monthly"))
    # symbols here are actually commodity function names (WTI, BRENT, ...).
    for name in symbols:
        try:
            series = client.commodities.by_name(name, interval=interval)
            stored = _upload_json(
                s3, target,
                f"commodities/{name.lower()}/{_today_slug()}.json",
                series.model_dump(by_alias=False),
            )
            result.keys.append(stored)
            result.uploaded_objects += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("commodity %s load failed: %s", name, exc)
            result.errors += 1


def _load_economics(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    for indicator in symbols:
        try:
            series = client.economics.by_name(indicator, **{k: v for k, v in extras.items() if k in {"interval", "maturity"}})
            stored = _upload_json(
                s3, target,
                f"economics/{indicator.lower()}/{_today_slug()}.json",
                series.model_dump(by_alias=False),
            )
            result.keys.append(stored)
            result.uploaded_objects += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("econ %s load failed: %s", indicator, exc)
            result.errors += 1


def _load_technicals(
    *,
    client: Any,
    s3: Any,
    target: MinioTarget,
    symbols: Iterable[str],
    date_range: Mapping[str, str],
    extras: Mapping[str, Any],
    result: BulkLoadResult,
) -> None:
    indicator = str(extras.get("indicator", "SMA")).upper()
    interval = str(extras.get("interval", "daily"))
    time_period = int(extras.get("time_period", 20))
    series_type = str(extras.get("series_type", "close"))
    for symbol in symbols:
        try:
            series = client.technicals.get(
                indicator,
                symbol,
                interval=interval,
                time_period=time_period,
                series_type=series_type,
            )
            stored = _upload_json(
                s3, target,
                f"technicals/{indicator.lower()}/{symbol}/{interval}/{_today_slug()}.json",
                series.model_dump(by_alias=False),
            )
            result.keys.append(stored)
            result.uploaded_objects += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("tech %s %s load failed: %s", indicator, symbol, exc)
            result.errors += 1


_LOADERS = {
    "timeseries": _load_timeseries,
    "intraday-backfill": _load_intraday_backfill,
    "fundamentals": _load_fundamentals,
    "universe": _load_universe,
    "news": _load_news,
    "earnings": _load_earnings,
    "fx": _load_fx,
    "crypto": _load_crypto,
    "commodities": _load_commodities,
    "economics": _load_economics,
    "technicals": _load_technicals,
    "bulk": _load_timeseries,
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _normalize_statements(payload: Mapping[str, Any]) -> dict:
    return {
        "symbol": payload.get("symbol"),
        "annual": [r.model_dump(by_alias=False) for r in payload.get("annual", [])],
        "quarterly": [r.model_dump(by_alias=False) for r in payload.get("quarterly", [])],
    }


def _normalize_earnings(payload: Any) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(by_alias=False)
    return dict(payload)


def _iter_months(start: Optional[str], end: Optional[str]) -> Iterable[str]:
    if not start:
        return []
    sd = _parse_month(start)
    ed = _parse_month(end or start)
    cursor = sd
    while cursor <= ed:
        yield cursor.strftime("%Y-%m")
        # move to first day of next month
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)


def _parse_month(value: str) -> date:
    for fmt in ("%Y-%m", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().replace(day=1)
        except ValueError:
            continue
    raise ValueError(f"invalid month {value!r}; expected YYYY-MM or YYYY-MM-DD")


def _slugify(value: str) -> str:
    return value.lower().replace(" ", "-")


def _today_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _split_pair(pair: str) -> tuple[str, str]:
    for sep in ("/", "-", ":"):
        if sep in pair:
            a, b = pair.split(sep, 1)
            return a.strip().upper(), b.strip().upper()
    if len(pair) == 6:
        return pair[:3].upper(), pair[3:].upper()
    raise ValueError(f"cannot split FX pair {pair!r}; use FROM/TO format")


__all__ = [
    "BulkLoadResult",
    "MinioTarget",
    "run_bulk_load",
]
