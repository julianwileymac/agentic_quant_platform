"""Equity entity-centric data product.

Aggregates everything an LLM agent typically needs to reason about a
single equity into one read-only object: instrument record (incl. the
polymorphic :class:`InstrumentEquity` columns), latest bars,
fundamentals, ratios, identifier links, news sentiment, and any
regulatory mentions tied to the issuer.

Reads only — never writes. Postgres ORM access is bounded; bar reads
go through :func:`aqp.data.iceberg_catalog.read_arrow` so backtests
can pin to a snapshot via :func:`read_arrow_at` if they need
time-travel.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, select

from aqp.data.products.base import BaseDataProduct, DataProductError
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    DatasetCatalog,
    IdentifierLink,
    Instrument,
)

logger = logging.getLogger(__name__)


class EquityEntity(BaseDataProduct):
    """Pre-aggregated read-only view of a single equity ``vt_symbol``."""

    product_kind = "equity"

    def __init__(
        self,
        vt_symbol: str,
        *,
        as_of: datetime | None = None,
        bars_lookback_days: int = 30,
    ) -> None:
        super().__init__(entity_id=vt_symbol, as_of=as_of)
        self.vt_symbol = str(vt_symbol)
        self.bars_lookback_days = max(int(bars_lookback_days), 1)

    def load(self) -> None:
        with get_session() as session:
            instrument = (
                session.execute(
                    select(Instrument).where(Instrument.vt_symbol == self.vt_symbol)
                )
                .scalars()
                .first()
            )
            if instrument is None:
                raise DataProductError(
                    f"no instrument with vt_symbol={self.vt_symbol!r}"
                )
            self._payload["instrument"] = self._instrument_to_dict(instrument)
            self._payload["identifiers"] = self._lookup_identifiers(
                session, instrument.id
            )
            self._payload["fundamentals"] = self._lookup_fundamentals(
                session, instrument.id
            )
            self._payload["ratios"] = self._lookup_ratios(session, instrument.id)
            self._payload["news"] = self._lookup_news(session, instrument.id)
            self._payload["regulatory"] = self._lookup_regulatory(
                session, self.vt_symbol
            )
            self._populate_provenance_from_catalog(session)

        self._payload["snapshot"] = self._lookup_recent_bars()
        self._populate_quality()
        self.add_lineage(
            transform_kind="data_product_load",
            target_table_id=None,
            summary=f"loaded equity entity for {self.vt_symbol}",
            actor=self.product_kind,
        )

    # ------------------------------------------------------------------
    # ORM aggregation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _instrument_to_dict(instrument: Instrument) -> dict[str, Any]:
        out: dict[str, Any] = {
            "vt_symbol": instrument.vt_symbol,
            "ticker": instrument.ticker,
            "exchange": instrument.exchange,
            "asset_class": instrument.asset_class,
            "security_type": instrument.security_type,
            "instrument_class": instrument.instrument_class,
            "issuer_id": instrument.issuer_id,
            "sector": instrument.sector,
            "industry": instrument.industry,
            "region": instrument.region,
            "currency": instrument.currency,
            "tick_size": instrument.tick_size,
            "multiplier": instrument.multiplier,
            "lot_size": instrument.lot_size,
            "is_active": bool(instrument.is_active),
            "tags": list(instrument.tags or []),
        }
        # Polymorphic columns: pick up any subclass-specific attributes
        # that exist on the loaded subclass instance. We never know in
        # advance whether we got InstrumentEquity, InstrumentETF, etc.
        for attr in (
            "issuer_cik",
            "isin",
            "cusip",
            "figi",
            "lei",
            "share_class",
            "primary_listing_venue",
            "listing_date",
            "delisting_date",
            "shares_outstanding",
            "float_shares",
            "is_adr",
            "country",
            "gics_sector",
            "gics_industry",
            "expense_ratio",
            "underlying_index",
            "is_leveraged",
            "leverage",
            "is_inverse",
            "replication",
            "aum",
            "inception_date",
        ):
            if hasattr(instrument, attr):
                value = getattr(instrument, attr)
                if value is not None:
                    if hasattr(value, "isoformat"):
                        out[attr] = value.isoformat()
                    else:
                        out[attr] = value
        return out

    def _lookup_identifiers(self, session, instrument_id: str) -> list[dict[str, Any]]:
        rows = (
            session.execute(
                select(IdentifierLink).where(
                    IdentifierLink.instrument_id == instrument_id
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "scheme": row.scheme,
                "value": row.value,
                "entity_kind": row.entity_kind,
                "confidence": float(row.confidence) if row.confidence is not None else None,
                "source_id": row.source_id,
            }
            for row in rows
        ]

    def _lookup_fundamentals(
        self, session, instrument_id: str
    ) -> list[dict[str, Any]]:
        try:
            from aqp.persistence.models_fundamentals import FinancialStatement
        except ImportError:
            return []
        try:
            rows = (
                session.execute(
                    select(FinancialStatement)
                    .where(FinancialStatement.instrument_id == instrument_id)
                    .order_by(desc(FinancialStatement.period_end))
                    .limit(4)
                )
                .scalars()
                .all()
            )
        except Exception:  # noqa: BLE001
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "period_end": _coerce_date(getattr(row, "period_end", None)),
                    "period_kind": getattr(row, "period_kind", None),
                    "currency": getattr(row, "currency", None),
                    "revenue": getattr(row, "revenue", None),
                    "net_income": getattr(row, "net_income", None),
                    "ebitda": getattr(row, "ebitda", None),
                    "operating_income": getattr(row, "operating_income", None),
                    "total_assets": getattr(row, "total_assets", None),
                    "total_equity": getattr(row, "total_equity", None),
                }
            )
        return out

    def _lookup_ratios(self, session, instrument_id: str) -> list[dict[str, Any]]:
        try:
            from aqp.persistence.models_fundamentals import FinancialRatios
        except ImportError:
            return []
        try:
            rows = (
                session.execute(
                    select(FinancialRatios)
                    .where(FinancialRatios.instrument_id == instrument_id)
                    .order_by(desc(FinancialRatios.period_end))
                    .limit(4)
                )
                .scalars()
                .all()
            )
        except Exception:  # noqa: BLE001
            return []
        return [
            {
                "period_end": _coerce_date(getattr(row, "period_end", None)),
                "pe_ratio": getattr(row, "pe_ratio", None),
                "pb_ratio": getattr(row, "pb_ratio", None),
                "debt_to_equity": getattr(row, "debt_to_equity", None),
                "current_ratio": getattr(row, "current_ratio", None),
                "return_on_equity": getattr(row, "return_on_equity", None),
                "return_on_assets": getattr(row, "return_on_assets", None),
                "gross_margin": getattr(row, "gross_margin", None),
                "operating_margin": getattr(row, "operating_margin", None),
                "net_margin": getattr(row, "net_margin", None),
            }
            for row in rows
        ]

    def _lookup_news(self, session, instrument_id: str) -> list[dict[str, Any]]:
        try:
            from aqp.persistence.models_news import NewsItemEntity, NewsItemRow
        except ImportError:
            return []
        try:
            stmt = (
                select(NewsItemRow, NewsItemEntity)
                .join(NewsItemEntity, NewsItemEntity.news_item_id == NewsItemRow.id)
                .where(NewsItemEntity.instrument_id == instrument_id)
                .order_by(desc(NewsItemRow.published_at))
                .limit(10)
            )
            rows = session.execute(stmt).all()
        except Exception:  # noqa: BLE001
            return []
        out: list[dict[str, Any]] = []
        for news_row, _link in rows:
            out.append(
                {
                    "headline": getattr(news_row, "headline", None),
                    "source_name": getattr(news_row, "source_name", None),
                    "source_url": getattr(news_row, "source_url", None),
                    "published_at": _coerce_datetime(
                        getattr(news_row, "published_at", None)
                    ),
                    "sentiment_score": getattr(news_row, "sentiment_score", None),
                }
            )
        return out

    def _lookup_regulatory(self, session, vt_symbol: str) -> dict[str, Any]:
        """CFPB / FDA / USPTO mentions tied to ``vt_symbol``.

        Only fetches counts to keep the context-pack token-efficient.
        Agents that want detail should call the regulatory MCP tool
        explicitly.
        """
        out: dict[str, Any] = {}
        try:
            from sqlalchemy import func

            from aqp.persistence.models_regulatory import (
                CfpbComplaint,
                FdaApplication,
                UsptoPatent,
            )

            for table_cls, key in (
                (CfpbComplaint, "cfpb_complaints"),
                (FdaApplication, "fda_applications"),
                (UsptoPatent, "uspto_patents"),
            ):
                try:
                    count = session.execute(
                        select(func.count())
                        .select_from(table_cls)
                        .where(getattr(table_cls, "vt_symbol") == vt_symbol)
                    ).scalar()
                    out[key] = int(count or 0)
                except Exception:  # noqa: BLE001
                    out[key] = None
        except ImportError:
            pass
        return out

    def _lookup_recent_bars(self) -> dict[str, Any]:
        """Best-effort Iceberg read of the most recent bars.

        Returns a compact ``{rows, last_close, last_timestamp}`` so the
        context pack stays small. Detailed bar reads should go through
        the iceberg MCP tool with a row filter.
        """
        try:
            from aqp.data.iceberg_catalog import read_arrow

            cutoff = self.as_of - timedelta(days=self.bars_lookback_days)
            try:
                from pyiceberg.expressions import EqualTo  # type: ignore

                row_filter = EqualTo("vt_symbol", self.vt_symbol)
            except Exception:  # noqa: BLE001
                row_filter = None
            arrow_tbl = read_arrow(
                "aqp_silver_alpha_vantage.daily_bars",
                columns=("vt_symbol", "timestamp", "close", "adjusted_close"),
                limit=self.bars_lookback_days,
                row_filter=row_filter,
            )
            if arrow_tbl is None or arrow_tbl.num_rows == 0:
                return {"rows": 0}
            close_arr = arrow_tbl.column("close").to_pylist()
            ts_arr = arrow_tbl.column("timestamp").to_pylist()
            self.add_iceberg_upstream("aqp_silver_alpha_vantage.daily_bars")
            return {
                "rows": int(arrow_tbl.num_rows),
                "last_close": close_arr[-1] if close_arr else None,
                "last_timestamp": (
                    ts_arr[-1].isoformat() if ts_arr and hasattr(ts_arr[-1], "isoformat") else None
                ),
                "lookback_days": self.bars_lookback_days,
                "since": cutoff.isoformat(),
            }
        except Exception:  # noqa: BLE001
            logger.debug(
                "EquityEntity._lookup_recent_bars failed for %s", self.vt_symbol, exc_info=True
            )
            return {"rows": 0}

    def _populate_provenance_from_catalog(self, session) -> None:
        try:
            rows = (
                session.execute(
                    select(DatasetCatalog).where(
                        DatasetCatalog.iceberg_identifier.in_(
                            self._provenance.upstream_iceberg_tables
                            or ["aqp_silver_alpha_vantage.daily_bars"]
                        )
                    )
                )
                .scalars()
                .all()
            )
        except Exception:  # noqa: BLE001
            rows = []
        for row in rows:
            self.add_provenance_source(row.provider)
            if row.business_metadata:
                reliability = row.business_metadata.get("reliability_score")
                if reliability is not None and self._quality.reliability_score is None:
                    self._quality.reliability_score = float(reliability)

    def _populate_quality(self) -> None:
        snapshot = self._payload.get("snapshot") or {}
        rows = snapshot.get("rows") or 0
        completeness = (
            min(rows / float(self.bars_lookback_days), 1.0) if rows else 0.0
        )
        last_ts = snapshot.get("last_timestamp")
        freshness = None
        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts)
                freshness = max((self.as_of - last_dt).total_seconds(), 0.0)
            except Exception:  # noqa: BLE001
                freshness = None
        self.set_quality(
            completeness=completeness,
            freshness_seconds=freshness,
            breakdown={"bars_rows": rows, "lookback_days": self.bars_lookback_days},
        )


def _coerce_date(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _coerce_datetime(value: Any) -> Any:
    return _coerce_date(value)


__all__ = ["EquityEntity"]
