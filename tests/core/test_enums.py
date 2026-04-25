"""Tests for the expanded enum catalog."""
from __future__ import annotations

from aqp.core.domain.enums import (
    AssetClass,
    BarAggregation,
    ContingencyType,
    CorporateActionKind,
    FilingType,
    IndustryClassificationScheme,
    InstrumentClass,
    Offset,
    OrderType,
    TimeInForce,
    TrailingOffsetType,
    TriggerType,
)


def test_asset_class_values():
    assert AssetClass.EQUITY == "equity"
    assert AssetClass.RATES == "rates"
    assert AssetClass.EVENT == "event"


def test_instrument_class_values():
    assert InstrumentClass.SPOT == "spot"
    assert InstrumentClass.OPTION == "option"
    assert InstrumentClass.PERPETUAL == "perpetual"
    assert InstrumentClass.BETTING == "betting"
    assert InstrumentClass.NFT == "nft"


def test_order_type_superset():
    # New values introduced by the expansion.
    assert OrderType.MARKET_IF_TOUCHED == "market_if_touched"
    assert OrderType.LIMIT_IF_TOUCHED == "limit_if_touched"
    assert OrderType.TRAILING_STOP_MARKET == "trailing_stop_market"
    assert OrderType.MARKET_TO_LIMIT == "market_to_limit"


def test_time_in_force_values():
    assert TimeInForce.DAY == "day"
    assert TimeInForce.GTC == "gtc"
    assert TimeInForce.FOK == "fok"
    assert TimeInForce.AT_THE_OPEN == "at_the_open"


def test_trigger_type_values():
    for name in ("BID_ASK", "LAST_PRICE", "DOUBLE_LAST", "MID_POINT", "MARK_PRICE"):
        assert hasattr(TriggerType, name)


def test_trailing_offset_values():
    assert TrailingOffsetType.PRICE == "price"
    assert TrailingOffsetType.BASIS_POINTS == "basis_points"
    assert TrailingOffsetType.TICKS == "ticks"
    assert TrailingOffsetType.PERCENTAGE == "percentage"


def test_contingency_type_values():
    for v in ("NONE", "OCO", "OUO", "OTO"):
        assert hasattr(ContingencyType, v)


def test_offset_futures_market():
    # vnpy-parity values covering Chinese futures brokers.
    assert Offset.OPEN == "open"
    assert Offset.CLOSE == "close"
    assert Offset.CLOSE_TODAY == "close_today"


def test_bar_aggregation_information_bars():
    # Lopez-de-Prado-style information bars should be present.
    for name in ("TICK_IMBALANCE", "VOLUME_IMBALANCE", "VALUE_IMBALANCE", "TICK_RUNS"):
        assert hasattr(BarAggregation, name)


def test_industry_classification_schemes():
    for name in ("SIC", "NAICS", "GICS", "TRBC", "ICB", "BICS", "NACE"):
        assert hasattr(IndustryClassificationScheme, name)


def test_filing_type_catalog():
    assert FilingType.ANNUAL_REPORT == "10-K"
    assert FilingType.QUARTERLY_REPORT == "10-Q"
    assert FilingType.CURRENT_REPORT == "8-K"
    assert FilingType.FORM_13F_HR == "13F-HR"


def test_corporate_action_kind_catalog():
    for name in ("SPLIT", "DIVIDEND", "SPIN_OFF", "MERGER", "IPO", "BUYBACK", "BANKRUPTCY"):
        assert hasattr(CorporateActionKind, name)
