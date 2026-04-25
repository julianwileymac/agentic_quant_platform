"""Managed security-universe snapshot sourced from Alpha Vantage."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import or_, select

from aqp.core.types import AssetClass, Exchange, SecurityType
from aqp.config import settings
from aqp.data.catalog import register_dataset_version
from aqp.data.sources.alpha_vantage.client import (
    AlphaVantageClient,
    AlphaVantageClientError,
)
from aqp.persistence.db import get_session
from aqp.persistence.models import Instrument

logger = logging.getLogger(__name__)


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _camel_to_snake(name: str) -> str:
    return _CAMEL_RE.sub("_", name).lower()


def _coerce_exchange(raw: str | None) -> str:
    value = str(raw or "").strip().upper()
    if "NASDAQ" in value:
        return Exchange.NASDAQ.value
    if "ARCA" in value:
        return Exchange.ARCA.value
    if "NYSE" in value:
        return Exchange.NYSE.value
    if "BATS" in value or "CBOE" in value or "BZX" in value:
        return Exchange.BATS.value
    return Exchange.LOCAL.value


def _coerce_asset_class(asset_type: str | None) -> tuple[str, str]:
    value = str(asset_type or "").strip().lower()
    if value in {"stock", "etf", "etn", "reit"}:
        return AssetClass.EQUITY.value, SecurityType.EQUITY.value
    if value in {"crypto", "digital currency"}:
        return AssetClass.CRYPTO.value, SecurityType.CRYPTO.value
    if value in {"forex", "fx"}:
        return AssetClass.FX.value, SecurityType.FOREX.value
    if value in {"index"}:
        return AssetClass.INDEX.value, SecurityType.INDEX.value
    return AssetClass.BASE.value, (value or SecurityType.BASE.value)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value or {})
    except Exception:
        return {}


class AlphaVantageUniverseService:
    """Fetch + normalize + upsert the instrument universe from Alpha Vantage."""

    def __init__(self, client: AlphaVantageClient | None = None) -> None:
        self.client = client or AlphaVantageClient()

    def fetch_snapshot(self, *, state: str = "active") -> pd.DataFrame:
        return self.client.listing_status(state=state)

    def normalize_snapshot(
        self,
        raw: pd.DataFrame,
        *,
        include_otc: bool = False,
        query: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()

        frame = raw.copy()
        frame.columns = [_camel_to_snake(str(c)) for c in frame.columns]
        if "symbol" not in frame.columns:
            raise AlphaVantageClientError("LISTING_STATUS response missing 'symbol' column")

        frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
        frame["name"] = (
            frame["name"].astype(str).str.strip()
            if "name" in frame.columns
            else ""
        )
        frame["exchange"] = (
            frame["exchange"].astype(str).str.strip()
            if "exchange" in frame.columns
            else ""
        )
        frame["asset_type"] = (
            frame["asset_type"].astype(str).str.strip()
            if "asset_type" in frame.columns
            else ""
        )
        frame["status"] = (
            frame["status"].astype(str).str.strip().str.lower()
            if "status" in frame.columns
            else ""
        )
        frame = frame[frame["symbol"] != ""]

        if not include_otc:
            frame = frame[
                ~frame["exchange"].str.upper().str.contains("OTC|PINK|GREY", regex=True)
            ]
        if query:
            q = query.strip().upper()
            if q:
                frame = frame[
                    frame["symbol"].str.contains(q, regex=False)
                    | frame["name"].str.upper().str.contains(q, regex=False)
                ]
        if limit is not None and int(limit) > 0:
            frame = frame.head(int(limit))

        rows: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for item in frame.to_dict(orient="records"):
            ticker = str(item.get("symbol") or "").strip().upper()
            if not ticker:
                continue
            exchange = _coerce_exchange(str(item.get("exchange") or ""))
            asset_class, security_type = _coerce_asset_class(str(item.get("asset_type") or ""))
            vt_symbol = f"{ticker}.{exchange}"
            rows.append(
                {
                    "ticker": ticker,
                    "exchange": exchange,
                    "vt_symbol": vt_symbol,
                    "asset_class": asset_class,
                    "security_type": security_type,
                    "currency": "USD",
                    "name": str(item.get("name") or "").strip(),
                    "asset_type": str(item.get("asset_type") or "").strip(),
                    "status": str(item.get("status") or "").strip().lower(),
                    "ipo_date": str(item.get("ipo_date") or "").strip(),
                    "delisting_date": str(item.get("delisting_date") or "").strip(),
                    "timestamp": now,
                }
            )

        if not rows:
            return pd.DataFrame()
        normalized = pd.DataFrame(rows)
        normalized = normalized.drop_duplicates(subset=["vt_symbol"], keep="first")
        return normalized.reset_index(drop=True)

    def sync_snapshot(
        self,
        *,
        state: str = "active",
        include_otc: bool = False,
        query: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        raw = self.fetch_snapshot(state=state)
        normalized = self.normalize_snapshot(
            raw,
            include_otc=include_otc,
            query=query,
            limit=limit,
        )
        if normalized.empty:
            return {
                "source": "alpha_vantage",
                "state": state,
                "ingested": 0,
                "created": 0,
                "updated": 0,
                "lineage": {},
            }

        now = datetime.now(timezone.utc)
        created = 0
        updated = 0
        vt_symbols = normalized["vt_symbol"].astype(str).tolist()
        with get_session() as session:
            existing_rows = session.execute(
                select(Instrument).where(Instrument.vt_symbol.in_(vt_symbols))
            ).scalars().all()
            existing = {row.vt_symbol: row for row in existing_rows}

            for item in normalized.to_dict(orient="records"):
                vt_symbol = str(item["vt_symbol"])
                record = existing.get(vt_symbol)
                if record is None:
                    meta = {
                        "alpha_vantage": {
                            "name": item.get("name"),
                            "asset_type": item.get("asset_type"),
                            "status": item.get("status"),
                            "ipo_date": item.get("ipo_date"),
                            "delisting_date": item.get("delisting_date"),
                            "synced_at": now.isoformat(),
                        }
                    }
                    session.add(
                        Instrument(
                            vt_symbol=vt_symbol,
                            ticker=str(item["ticker"]),
                            exchange=str(item["exchange"]),
                            asset_class=str(item["asset_class"]),
                            security_type=str(item["security_type"]),
                            identifiers={
                                "vt_symbol": vt_symbol,
                                "ticker": str(item["ticker"]),
                                "alpha_vantage_symbol": str(item["ticker"]),
                            },
                            currency=str(item.get("currency") or "USD"),
                            tags=["alpha_vantage"],
                            meta=meta,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    created += 1
                    continue

                record.ticker = str(item["ticker"])
                record.exchange = str(item["exchange"])
                record.asset_class = str(item["asset_class"])
                record.security_type = str(item["security_type"])
                record.currency = str(item.get("currency") or record.currency or "USD")

                identifiers = _as_dict(record.identifiers)
                identifiers.setdefault("vt_symbol", vt_symbol)
                identifiers.setdefault("ticker", str(item["ticker"]))
                identifiers["alpha_vantage_symbol"] = str(item["ticker"])
                record.identifiers = identifiers

                tags = list(record.tags or [])
                if "alpha_vantage" not in tags:
                    tags.append("alpha_vantage")
                record.tags = tags

                meta = _as_dict(record.meta)
                av_meta = _as_dict(meta.get("alpha_vantage"))
                av_meta.update(
                    {
                        "name": item.get("name"),
                        "asset_type": item.get("asset_type"),
                        "status": item.get("status"),
                        "ipo_date": item.get("ipo_date"),
                        "delisting_date": item.get("delisting_date"),
                        "synced_at": now.isoformat(),
                    }
                )
                meta["alpha_vantage"] = av_meta
                record.meta = meta
                record.updated_at = now
                session.add(record)
                updated += 1

        lineage_df = normalized[
            [
                "timestamp",
                "vt_symbol",
                "ticker",
                "exchange",
                "asset_type",
                "status",
            ]
        ].copy()
        lineage: dict[str, Any] = {}
        try:
            lineage = register_dataset_version(
                name="universe.alpha_vantage",
                provider="alpha_vantage",
                domain="security.master",
                df=lineage_df,
                storage_uri=None,
                frequency=None,
                meta={
                    "state": state,
                    "include_otc": bool(include_otc),
                    "query": query or "",
                    "limit": int(limit) if limit is not None else None,
                },
                file_count=1,
            )
        except Exception:
            logger.debug("alpha_vantage universe lineage registration skipped", exc_info=True)

        return {
            "source": "alpha_vantage",
            "state": state,
            "ingested": int(len(normalized)),
            "created": int(created),
            "updated": int(updated),
            "lineage": lineage,
        }

    def list_snapshot(
        self,
        *,
        limit: int = 200,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        with get_session() as session:
            stmt = select(Instrument)
            if query:
                q = f"%{query.strip()}%"
                stmt = stmt.where(
                    or_(
                        Instrument.ticker.ilike(q),
                        Instrument.vt_symbol.ilike(q),
                        Instrument.sector.ilike(q),
                        Instrument.industry.ilike(q),
                    )
                )
            stmt = stmt.order_by(Instrument.ticker.asc()).limit(max(1, int(limit)))
            rows = session.execute(stmt).scalars().all()

            out: list[dict[str, Any]] = []
            for row in rows:
                out.append(
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
                )
            return out

    def default_symbols(self, *, limit: int | None = None) -> list[str]:
        cap = int(limit if limit is not None else settings.managed_universe_limit)
        rows = self.list_snapshot(limit=max(1, cap))
        return [str(row.get("ticker") or "").strip().upper() for row in rows if row.get("ticker")]
