"""Normalization strategy tests."""
from __future__ import annotations

import pytest

from aqp.data.normalization import (
    EquityNormalization,
    MacroNormalization,
    NewsNormalization,
    OptionsNormalization,
    RegulatoryNormalization,
    get_normalization_strategy,
    list_normalization_strategies,
)


def _arrow_table(columns: dict) -> any:
    pa = pytest.importorskip("pyarrow")
    return pa.table(columns)


def test_strategy_registry_contains_canonical_aliases() -> None:
    aliases = {entry["alias"] for entry in list_normalization_strategies()}
    assert {
        "equity",
        "options",
        "macro",
        "regulatory",
        "news",
        "microstructure",
    } <= aliases


def test_get_normalization_strategy_returns_instance() -> None:
    strategy = get_normalization_strategy("equity")
    assert isinstance(strategy, EquityNormalization)


def test_unknown_alias_raises() -> None:
    with pytest.raises(KeyError):
        get_normalization_strategy("definitely-not-a-real-alias")


def test_equity_normalization_renames_provider_columns() -> None:
    pa = pytest.importorskip("pyarrow")
    table = pa.table(
        {
            "Date": pa.array(["2023-01-01", "2023-01-02"]),
            "Symbol": pa.array(["AAPL.NASDAQ", "AAPL.NASDAQ"]),
            "Open": pa.array([100.0, 101.0]),
            "High": pa.array([102.0, 103.0]),
            "Low": pa.array([99.0, 100.0]),
            "Close": pa.array([101.0, 102.0]),
            "Adj Close": pa.array([101.0, 102.0]),
            "Volume": pa.array([1_000_000, 1_100_000]),
        }
    )
    result = EquityNormalization().normalize(table)
    names = result.table.column_names
    assert "vt_symbol" in names
    assert "timestamp" in names
    assert "adjusted_close" in names
    # Original casing should not survive
    assert "Adj Close" not in names
    assert result.rows_in == 2


def test_options_normalization_renames_greeks() -> None:
    pa = pytest.importorskip("pyarrow")
    table = pa.table(
        {
            "Strike": pa.array([100.0, 110.0]),
            "OptionType": pa.array(["C", "P"]),
            "Bid": pa.array([1.0, 0.5]),
            "Ask": pa.array([1.1, 0.6]),
            "ImpliedVolatility": pa.array([0.25, 0.30]),
        }
    )
    result = OptionsNormalization().normalize(table)
    names = result.table.column_names
    assert "strike" in names
    assert "option_type" in names
    assert "implied_volatility" in names


def test_macro_normalization_renames_value_column() -> None:
    pa = pytest.importorskip("pyarrow")
    table = pa.table(
        {
            "DATE": pa.array(["2023-01-01"]),
            "VALUE": pa.array([1.5]),
            "id": pa.array(["DGS10"]),
        }
    )
    result = MacroNormalization().normalize(table)
    names = result.table.column_names
    assert "observation_date" in names
    assert "value" in names
    assert "series_id" in names


def test_regulatory_normalization_renames_filing_columns() -> None:
    pa = pytest.importorskip("pyarrow")
    table = pa.table(
        {
            "complaint_id": pa.array(["123"]),
            "submitter": pa.array(["Consumer A"]),
            "filed_date": pa.array(["2023-05-10"]),
        }
    )
    result = RegulatoryNormalization().normalize(table)
    names = result.table.column_names
    assert "regulatory_id" in names
    assert "submitting_party" in names
    assert "filing_date" in names


def test_news_normalization_renames_article_columns() -> None:
    pa = pytest.importorskip("pyarrow")
    table = pa.table(
        {
            "title": pa.array(["Headline A"]),
            "summary": pa.array(["Body text."]),
            "Sentiment": pa.array([0.5]),
            "Source": pa.array(["BloomTimes"]),
        }
    )
    result = NewsNormalization().normalize(table)
    names = result.table.column_names
    assert "headline" in names
    assert "body" in names
    assert "sentiment_score" in names
    assert "source_name" in names


def test_normalization_records_contract_violations() -> None:
    pa = pytest.importorskip("pyarrow")
    from aqp.data.catalog.active_metadata import DataContract

    table = pa.table({"Close": pa.array([1.0])})
    contract = DataContract(
        columns=[
            {"name": "vt_symbol", "type": "string", "required": True},
            {"name": "close", "type": "float", "required": True},
        ]
    )
    result = EquityNormalization().normalize(table, contract=contract)
    assert any("vt_symbol" in v for v in result.contract_violations)
