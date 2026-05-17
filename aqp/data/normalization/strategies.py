"""Concrete normalization strategies for AQP Silver-layer data.

Each strategy:

- Renames provider-specific columns to the canonical Silver names
  (eg. ``Adj Close`` -> ``adjusted_close``)
- Coerces types to the contract type-family
- Adds ``vt_symbol`` / ``as_of_utc`` / ``ingested_at`` where relevant
- Emits a ``schema_drift`` lineage event for unexpected columns

All strategies are pure functions of (arrow_table, contract). They
must not write to Iceberg, Postgres, or Redis directly — those side
effects live above the strategy layer.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.data.catalog.active_metadata import (
    DataContract,
    validate_contract_against_schema,
)
from aqp.data.normalization.base import (
    BaseNormalizationStrategy,
    NormalizationResult,
    register_normalization_strategy,
)

logger = logging.getLogger(__name__)


# Common provider-name maps so individual strategies don't repeat
# themselves. These are intentionally case-sensitive — providers
# usually serve the same case across calls and case-folding can
# silently mask schema drift.
_EQUITY_RENAMES = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adjusted_close",
    "AdjClose": "adjusted_close",
    "adj_close": "adjusted_close",
    "Volume": "volume",
    "Date": "timestamp",
    "Datetime": "timestamp",
    "Symbol": "vt_symbol",
    "ticker": "vt_symbol",
    "symbol": "vt_symbol",
}

_OPTIONS_RENAMES = {
    "underlying": "underlying_vt_symbol",
    "underlying_symbol": "underlying_vt_symbol",
    "Strike": "strike",
    "ExpirationDate": "expiration_date",
    "expiration": "expiration_date",
    "OptionType": "option_type",
    "right": "option_type",
    "Bid": "bid",
    "Ask": "ask",
    "Last": "last_price",
    "ImpliedVolatility": "implied_volatility",
    "Delta": "delta",
    "Gamma": "gamma",
    "Vega": "vega",
    "Theta": "theta",
    "Rho": "rho",
    "OpenInterest": "open_interest",
    "Volume": "volume",
}

_MACRO_RENAMES = {
    "DATE": "observation_date",
    "Date": "observation_date",
    "VALUE": "value",
    "Value": "value",
    "series": "series_id",
    "id": "series_id",
}

_REGULATORY_RENAMES = {
    "complaint_id": "regulatory_id",
    "patent_number": "regulatory_id",
    "application_number": "regulatory_id",
    "trademark_serial_number": "regulatory_id",
    "submitter": "submitting_party",
    "filed_date": "filing_date",
    "Date Received": "filing_date",
}

_NEWS_RENAMES = {
    "title": "headline",
    "Headline": "headline",
    "summary": "body",
    "content": "body",
    "Sentiment": "sentiment_score",
    "score": "sentiment_score",
    "Source": "source_name",
    "url": "source_url",
}

_MICROSTRUCTURE_RENAMES = {
    "Symbol": "vt_symbol",
    "BidPrice": "bid_price",
    "AskPrice": "ask_price",
    "BidSize": "bid_size",
    "AskSize": "ask_size",
    "Time": "timestamp",
    "ts": "timestamp",
    "Trade Price": "last_price",
    "Trade Size": "last_size",
}


def _add_ingested_timestamp(table: Any) -> Any:
    """Append ``ingested_at`` UTC timestamp column if missing."""
    try:
        import pyarrow as pa
    except ImportError:
        return table
    if table is None or "ingested_at" in table.column_names:
        return table
    row_count = int(table.num_rows or 0)
    if row_count == 0:
        return table
    now = datetime.utcnow()
    return table.append_column(
        "ingested_at",
        pa.array([now] * row_count, type=pa.timestamp("us")),
    )


def _drop_empty_rows(table: Any, required_cols: list[str]) -> tuple[Any, int]:
    """Drop rows where every required column is null."""
    try:
        import pyarrow as pa  # noqa: F401
        import pyarrow.compute as pc
    except ImportError:
        return table, 0
    if table is None:
        return table, 0
    have = [c for c in required_cols if c in table.column_names]
    if not have:
        return table, 0
    mask = None
    for col in have:
        col_arr = table.column(col)
        not_null = pc.is_valid(col_arr)
        mask = not_null if mask is None else pc.or_kleene(mask, not_null)
    if mask is None:
        return table, 0
    rows_in = int(table.num_rows or 0)
    filtered = table.filter(mask)
    rows_out = int(filtered.num_rows or 0)
    return filtered, rows_in - rows_out


# ---------------------------------------------------------------------------
# Concrete strategies
# ---------------------------------------------------------------------------


@register_normalization_strategy("equity")
class EquityNormalization(BaseNormalizationStrategy):
    """Equity OHLCV bars + identifiers."""

    description = "Coerce equity bar feeds to (vt_symbol, timestamp, OHLCV, adjusted_close)."
    handles_domains = ("market.bars", "equity.bars", "equity.daily")

    def normalize(
        self,
        table: Any,
        *,
        contract: DataContract | None = None,
    ) -> NormalizationResult:
        rows_in = int(getattr(table, "num_rows", 0) or 0)
        renamed = self.safe_rename(table, _EQUITY_RENAMES)
        renamed, dropped = _drop_empty_rows(renamed, ["close", "adjusted_close", "volume"])
        renamed = _add_ingested_timestamp(renamed)
        violations = (
            validate_contract_against_schema(contract, getattr(renamed, "schema", None))
            if contract is not None
            else []
        )
        drift = self._detect_drift_columns(renamed, contract)
        if drift:
            self._emit_drift(self.alias, drift, contract)
        return NormalizationResult(
            table=renamed,
            rows_in=rows_in,
            rows_out=int(getattr(renamed, "num_rows", 0) or 0),
            rows_dropped=dropped,
            contract_violations=violations,
            drift_columns=drift,
            notes=[f"renamed {len(_EQUITY_RENAMES)} candidate columns"],
        )


@register_normalization_strategy("options")
class OptionsNormalization(BaseNormalizationStrategy):
    """Options chain with greeks + IV."""

    description = "Coerce options chain rows to (underlying_vt_symbol, expiration_date, strike, option_type, ...)."
    handles_domains = ("options.chain", "options.greeks", "derivatives.options")

    def normalize(
        self,
        table: Any,
        *,
        contract: DataContract | None = None,
    ) -> NormalizationResult:
        rows_in = int(getattr(table, "num_rows", 0) or 0)
        renamed = self.safe_rename(table, _OPTIONS_RENAMES)
        renamed, dropped = _drop_empty_rows(
            renamed, ["bid", "ask", "last_price", "implied_volatility"]
        )
        renamed = _add_ingested_timestamp(renamed)
        violations = (
            validate_contract_against_schema(contract, getattr(renamed, "schema", None))
            if contract is not None
            else []
        )
        drift = self._detect_drift_columns(renamed, contract)
        if drift:
            self._emit_drift(self.alias, drift, contract)
        return NormalizationResult(
            table=renamed,
            rows_in=rows_in,
            rows_out=int(getattr(renamed, "num_rows", 0) or 0),
            rows_dropped=dropped,
            contract_violations=violations,
            drift_columns=drift,
            notes=[f"renamed {len(_OPTIONS_RENAMES)} candidate columns"],
        )


@register_normalization_strategy("macro")
class MacroNormalization(BaseNormalizationStrategy):
    """Macroeconomic series + observations."""

    description = "Coerce FRED / BLS / Treasury macro feeds to (series_id, observation_date, value)."
    handles_domains = ("macro.series", "macro.observation", "fred", "bls", "treasury")

    def normalize(
        self,
        table: Any,
        *,
        contract: DataContract | None = None,
    ) -> NormalizationResult:
        rows_in = int(getattr(table, "num_rows", 0) or 0)
        renamed = self.safe_rename(table, _MACRO_RENAMES)
        renamed, dropped = _drop_empty_rows(renamed, ["value"])
        renamed = _add_ingested_timestamp(renamed)
        violations = (
            validate_contract_against_schema(contract, getattr(renamed, "schema", None))
            if contract is not None
            else []
        )
        drift = self._detect_drift_columns(renamed, contract)
        if drift:
            self._emit_drift(self.alias, drift, contract)
        return NormalizationResult(
            table=renamed,
            rows_in=rows_in,
            rows_out=int(getattr(renamed, "num_rows", 0) or 0),
            rows_dropped=dropped,
            contract_violations=violations,
            drift_columns=drift,
            notes=[f"renamed {len(_MACRO_RENAMES)} candidate columns"],
        )


@register_normalization_strategy("regulatory")
class RegulatoryNormalization(BaseNormalizationStrategy):
    """CFPB / FDA / USPTO regulatory artifacts."""

    description = "Coerce CFPB complaints, FDA filings, USPTO records to a unified regulatory schema."
    handles_domains = (
        "regulatory.cfpb",
        "regulatory.fda",
        "regulatory.uspto",
        "regulatory.sec",
    )

    def normalize(
        self,
        table: Any,
        *,
        contract: DataContract | None = None,
    ) -> NormalizationResult:
        rows_in = int(getattr(table, "num_rows", 0) or 0)
        renamed = self.safe_rename(table, _REGULATORY_RENAMES)
        renamed = _add_ingested_timestamp(renamed)
        violations = (
            validate_contract_against_schema(contract, getattr(renamed, "schema", None))
            if contract is not None
            else []
        )
        drift = self._detect_drift_columns(renamed, contract)
        if drift:
            self._emit_drift(self.alias, drift, contract)
        return NormalizationResult(
            table=renamed,
            rows_in=rows_in,
            rows_out=int(getattr(renamed, "num_rows", 0) or 0),
            rows_dropped=0,
            contract_violations=violations,
            drift_columns=drift,
            notes=[f"renamed {len(_REGULATORY_RENAMES)} candidate columns"],
        )


@register_normalization_strategy("news")
class NewsNormalization(BaseNormalizationStrategy):
    """News articles + sentiment."""

    description = "Coerce news/sentiment feeds to (headline, body, source_url, source_name, sentiment_score, vt_symbol_refs)."
    handles_domains = ("news.article", "news.sentiment", "alt.news")

    def normalize(
        self,
        table: Any,
        *,
        contract: DataContract | None = None,
    ) -> NormalizationResult:
        rows_in = int(getattr(table, "num_rows", 0) or 0)
        renamed = self.safe_rename(table, _NEWS_RENAMES)
        renamed, dropped = _drop_empty_rows(renamed, ["headline", "body"])
        renamed = _add_ingested_timestamp(renamed)
        violations = (
            validate_contract_against_schema(contract, getattr(renamed, "schema", None))
            if contract is not None
            else []
        )
        drift = self._detect_drift_columns(renamed, contract)
        if drift:
            self._emit_drift(self.alias, drift, contract)
        return NormalizationResult(
            table=renamed,
            rows_in=rows_in,
            rows_out=int(getattr(renamed, "num_rows", 0) or 0),
            rows_dropped=dropped,
            contract_violations=violations,
            drift_columns=drift,
            notes=[f"renamed {len(_NEWS_RENAMES)} candidate columns"],
        )


@register_normalization_strategy("microstructure")
class MicrostructureNormalization(BaseNormalizationStrategy):
    """Tick / order-book / quote-level data."""

    description = "Coerce L1/L2 order-book and tick feeds to (vt_symbol, timestamp, bid/ask price/size, last_price/size)."
    handles_domains = ("microstructure.tick", "microstructure.l1", "microstructure.l2")

    def normalize(
        self,
        table: Any,
        *,
        contract: DataContract | None = None,
    ) -> NormalizationResult:
        rows_in = int(getattr(table, "num_rows", 0) or 0)
        renamed = self.safe_rename(table, _MICROSTRUCTURE_RENAMES)
        renamed, dropped = _drop_empty_rows(
            renamed, ["bid_price", "ask_price", "last_price"]
        )
        renamed = _add_ingested_timestamp(renamed)
        violations = (
            validate_contract_against_schema(contract, getattr(renamed, "schema", None))
            if contract is not None
            else []
        )
        drift = self._detect_drift_columns(renamed, contract)
        if drift:
            self._emit_drift(self.alias, drift, contract)
        return NormalizationResult(
            table=renamed,
            rows_in=rows_in,
            rows_out=int(getattr(renamed, "num_rows", 0) or 0),
            rows_dropped=dropped,
            contract_violations=violations,
            drift_columns=drift,
            notes=[f"renamed {len(_MICROSTRUCTURE_RENAMES)} candidate columns"],
        )


__all__ = [
    "EquityNormalization",
    "MacroNormalization",
    "MicrostructureNormalization",
    "NewsNormalization",
    "OptionsNormalization",
    "RegulatoryNormalization",
]
