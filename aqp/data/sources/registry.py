"""Thin facade over the ``data_sources`` table with a safe fallback."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource

logger = logging.getLogger(__name__)


_FALLBACK_SOURCE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "builtin-yfinance",
        "name": "yfinance",
        "display_name": "Yahoo Finance (yfinance)",
        "kind": "sdk",
        "vendor": "Yahoo",
        "auth_type": "none",
        "base_url": "https://finance.yahoo.com",
        "protocol": "https/json",
        "capabilities": {"domains": ["market.bars", "market.fundamentals", "news"]},
        "rate_limits": {"req_per_minute": 60},
        "credentials_ref": None,
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-polygon",
        "name": "polygon",
        "display_name": "Polygon.io",
        "kind": "rest_api",
        "vendor": "Polygon.io",
        "auth_type": "api_key",
        "base_url": "https://api.polygon.io",
        "protocol": "https/json",
        "capabilities": {"domains": ["market.bars", "market.quotes", "market.ticks"]},
        "rate_limits": {"req_per_minute": 5},
        "credentials_ref": "AQP_POLYGON_API_KEY",
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-alpha-vantage",
        "name": "alpha_vantage",
        "display_name": "Alpha Vantage",
        "kind": "rest_api",
        "vendor": "Alpha Vantage",
        "auth_type": "api_key",
        "base_url": "https://www.alphavantage.co/query",
        "protocol": "https/json",
        "capabilities": {
            "domains": [
                "market.bars",
                "market.quotes",
                "market.status",
                "fundamentals.overview",
                "fundamentals.statements",
                "fundamentals.earnings",
                "news.sentiment",
                "derivatives.options",
                "fx",
                "crypto",
                "commodities",
                "economic.series",
                "technical.indicators",
                "indices",
            ]
        },
        "rate_limits": {"req_per_minute": 75},
        "credentials_ref": "AQP_ALPHA_VANTAGE_API_KEY",
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-ibkr",
        "name": "ibkr",
        "display_name": "Interactive Brokers",
        "kind": "gateway",
        "vendor": "Interactive Brokers",
        "auth_type": "session",
        "base_url": None,
        "protocol": "tcp",
        "capabilities": {"domains": ["market.bars", "market.quotes", "execution"]},
        "rate_limits": {},
        "credentials_ref": "IBKR_PROFILE",
        "enabled": False,
        "meta": {},
    },
    {
        "id": "builtin-alpaca",
        "name": "alpaca",
        "display_name": "Alpaca",
        "kind": "rest_api",
        "vendor": "Alpaca",
        "auth_type": "api_key",
        "base_url": "https://paper-api.alpaca.markets",
        "protocol": "https/json",
        "capabilities": {"domains": ["market.bars", "market.quotes", "trading"]},
        "rate_limits": {"req_per_minute": 200},
        "credentials_ref": "AQP_ALPACA_KEY_ID/AQP_ALPACA_SECRET_KEY",
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-ccxt",
        "name": "ccxt",
        "display_name": "CCXT Exchanges",
        "kind": "sdk",
        "vendor": "CCXT",
        "auth_type": "optional_api_key",
        "base_url": None,
        "protocol": "https/json",
        "capabilities": {"domains": ["market.bars", "market.orderbook", "crypto"]},
        "rate_limits": {},
        "credentials_ref": "AQP_CCXT_EXCHANGE",
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-local",
        "name": "local",
        "display_name": "Local Parquet Files",
        "kind": "local_file",
        "vendor": "AQP",
        "auth_type": "none",
        "base_url": None,
        "protocol": "file/parquet",
        "capabilities": {"domains": ["market.bars", "features", "labels"]},
        "rate_limits": {},
        "credentials_ref": None,
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-fred",
        "name": "fred",
        "display_name": "FRED (Federal Reserve Economic Data)",
        "kind": "rest_api",
        "vendor": "Federal Reserve Bank of St. Louis",
        "auth_type": "api_key",
        "base_url": "https://api.stlouisfed.org/fred",
        "protocol": "https/json",
        "capabilities": {"domains": ["economic.series"]},
        "rate_limits": {"req_per_minute": 120},
        "credentials_ref": "AQP_FRED_API_KEY",
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-sec-edgar",
        "name": "sec_edgar",
        "display_name": "SEC EDGAR filings",
        "kind": "sdk",
        "vendor": "U.S. Securities and Exchange Commission",
        "auth_type": "identity",
        "base_url": "https://www.sec.gov",
        "protocol": "https/json+xml",
        "capabilities": {
            "domains": [
                "filings.index",
                "filings.xbrl",
                "filings.insider",
                "filings.ownership",
                "filings.events",
            ]
        },
        "rate_limits": {"req_per_second": 10},
        "credentials_ref": "AQP_SEC_EDGAR_IDENTITY",
        "enabled": True,
        "meta": {},
    },
    {
        "id": "builtin-gdelt",
        "name": "gdelt",
        "display_name": "GDELT Global Knowledge Graph 2.0",
        "kind": "file_manifest",
        "vendor": "The GDELT Project",
        "auth_type": "none",
        "base_url": "http://data.gdeltproject.org/gkg",
        "protocol": "https/csv.zip",
        "capabilities": {
            "domains": ["events.gdelt", "news"],
            "supports_bigquery": True,
            "bigquery_table": "gdelt-bq.gdeltv2.gkg",
        },
        "rate_limits": {},
        "credentials_ref": None,
        "enabled": True,
        "meta": {},
    },
)


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    try:
        return dict(value)
    except Exception:
        return {}


def _fallback_sources(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    rows = []
    for spec in _FALLBACK_SOURCE_SPECS:
        row = {
            **spec,
            "capabilities": _as_mapping(spec.get("capabilities")),
            "rate_limits": _as_mapping(spec.get("rate_limits")),
            "meta": _as_mapping(spec.get("meta")),
            "created_at": now,
            "updated_at": now,
        }
        if enabled_only and not row["enabled"]:
            continue
        rows.append(row)
    return sorted(rows, key=lambda row: row["name"])


def _fallback_source(name: str) -> dict[str, Any] | None:
    for row in _fallback_sources():
        if row["name"] == name:
            return row
    return None


def _row_to_dict(row: DataSource) -> dict[str, Any]:
    now = datetime.utcnow()
    return {
        "id": row.id,
        "name": row.name,
        "display_name": row.display_name,
        "kind": row.kind,
        "vendor": row.vendor,
        "auth_type": row.auth_type,
        "base_url": row.base_url,
        "protocol": row.protocol,
        "capabilities": _as_mapping(row.capabilities),
        "rate_limits": _as_mapping(row.rate_limits),
        "credentials_ref": row.credentials_ref,
        "enabled": bool(row.enabled),
        "meta": _as_mapping(row.meta),
        "created_at": row.created_at or now,
        "updated_at": row.updated_at or now,
    }


def list_data_sources(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    """Return every ``DataSource`` row as a plain dict list."""
    try:
        with get_session() as session:
            stmt = select(DataSource)
            if enabled_only:
                stmt = stmt.where(DataSource.enabled.is_(True))
            rows = session.execute(stmt.order_by(DataSource.name)).scalars().all()
            if rows:
                return [_row_to_dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("Falling back to builtin sources; table unavailable: %s", exc)
    return _fallback_sources(enabled_only=enabled_only)


def get_data_source(name: str) -> dict[str, Any] | None:
    """Return one ``DataSource`` row (by ``name``) as a dict, or ``None``."""
    try:
        with get_session() as session:
            row = session.execute(
                select(DataSource).where(DataSource.name == name).limit(1)
            ).scalar_one_or_none()
            return _row_to_dict(row) if row else _fallback_source(name)
    except SQLAlchemyError as exc:
        logger.warning("Falling back to builtin source %r: %s", name, exc)
        return _fallback_source(name)


def _fallback_upsert(
    *,
    name: str,
    display_name: str | None = None,
    kind: str | None = None,
    vendor: str | None = None,
    auth_type: str | None = None,
    base_url: str | None = None,
    protocol: str | None = None,
    capabilities: dict[str, Any] | None = None,
    rate_limits: dict[str, Any] | None = None,
    credentials_ref: str | None = None,
    enabled: bool | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.utcnow()
    baseline = _fallback_source(name) or {
        "id": f"builtin-{name}",
        "name": name,
        "display_name": name,
        "kind": "rest_api",
        "vendor": None,
        "auth_type": "none",
        "base_url": None,
        "protocol": "https/json",
        "capabilities": {},
        "rate_limits": {},
        "credentials_ref": None,
        "enabled": True,
        "meta": {},
        "created_at": now,
        "updated_at": now,
    }
    return {
        **baseline,
        "display_name": display_name or baseline["display_name"],
        "kind": kind or baseline["kind"],
        "vendor": vendor if vendor is not None else baseline["vendor"],
        "auth_type": auth_type or baseline["auth_type"],
        "base_url": base_url if base_url is not None else baseline["base_url"],
        "protocol": protocol or baseline["protocol"],
        "capabilities": {
            **_as_mapping(baseline.get("capabilities")),
            **_as_mapping(capabilities),
        },
        "rate_limits": {
            **_as_mapping(baseline.get("rate_limits")),
            **_as_mapping(rate_limits),
        },
        "credentials_ref": (
            credentials_ref
            if credentials_ref is not None
            else baseline["credentials_ref"]
        ),
        "enabled": bool(enabled) if enabled is not None else bool(baseline["enabled"]),
        "meta": {**_as_mapping(baseline.get("meta")), **_as_mapping(meta)},
        "updated_at": now,
    }


def upsert_data_source(
    *,
    name: str,
    display_name: str | None = None,
    kind: str | None = None,
    vendor: str | None = None,
    auth_type: str | None = None,
    base_url: str | None = None,
    protocol: str | None = None,
    capabilities: dict[str, Any] | None = None,
    rate_limits: dict[str, Any] | None = None,
    credentials_ref: str | None = None,
    enabled: bool | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or patch a ``DataSource`` row keyed on ``name``."""
    try:
        with get_session() as session:
            row = session.execute(
                select(DataSource).where(DataSource.name == name).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = DataSource(
                    name=name,
                    display_name=display_name or name,
                    kind=kind or "rest_api",
                    vendor=vendor,
                    auth_type=auth_type or "none",
                    base_url=base_url,
                    protocol=protocol or "https/json",
                    capabilities=_as_mapping(capabilities),
                    rate_limits=_as_mapping(rate_limits),
                    credentials_ref=credentials_ref,
                    enabled=bool(enabled) if enabled is not None else True,
                    meta=_as_mapping(meta),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
                return _row_to_dict(row)

            if display_name is not None:
                row.display_name = display_name
            if kind is not None:
                row.kind = kind
            if vendor is not None:
                row.vendor = vendor
            if auth_type is not None:
                row.auth_type = auth_type
            if base_url is not None:
                row.base_url = base_url
            if protocol is not None:
                row.protocol = protocol
            if capabilities is not None:
                row.capabilities = {
                    **_as_mapping(row.capabilities),
                    **_as_mapping(capabilities),
                }
            if rate_limits is not None:
                row.rate_limits = {
                    **_as_mapping(row.rate_limits),
                    **_as_mapping(rate_limits),
                }
            if credentials_ref is not None:
                row.credentials_ref = credentials_ref
            if enabled is not None:
                row.enabled = bool(enabled)
            if meta is not None:
                row.meta = {**_as_mapping(row.meta), **_as_mapping(meta)}
            row.updated_at = datetime.utcnow()
            session.add(row)
            session.flush()
            return _row_to_dict(row)
    except SQLAlchemyError as exc:
        logger.warning("Upsert fallback for source %r: %s", name, exc)
        return _fallback_upsert(
            name=name,
            display_name=display_name,
            kind=kind,
            vendor=vendor,
            auth_type=auth_type,
            base_url=base_url,
            protocol=protocol,
            capabilities=capabilities,
            rate_limits=rate_limits,
            credentials_ref=credentials_ref,
            enabled=enabled,
            meta=meta,
        )


def set_data_source_enabled(name: str, enabled: bool) -> dict[str, Any] | None:
    """Toggle ``enabled`` for a source. Returns the patched row, or ``None``."""
    try:
        with get_session() as session:
            row = session.execute(
                select(DataSource).where(DataSource.name == name).limit(1)
            ).scalar_one_or_none()
            if row is None:
                fallback = _fallback_source(name)
                if fallback is None:
                    return None
                fallback["enabled"] = bool(enabled)
                fallback["updated_at"] = datetime.utcnow()
                return fallback
            row.enabled = bool(enabled)
            row.updated_at = datetime.utcnow()
            session.add(row)
            session.flush()
            return _row_to_dict(row)
    except SQLAlchemyError as exc:
        logger.warning("Enable fallback for source %r: %s", name, exc)
        fallback = _fallback_source(name)
        if fallback is None:
            return None
        fallback["enabled"] = bool(enabled)
        fallback["updated_at"] = datetime.utcnow()
        return fallback
