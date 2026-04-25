"""Tests for the polymorphic Instrument hierarchy + (AssetClass, InstrumentClass) dispatch."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from aqp.core.domain.enums import (
    AssetClass,
    InstrumentClass,
    OptionKind,
    OptionStyle,
    SettlementType,
)
from aqp.core.domain.identifiers import InstrumentId, Symbol2, Venue
from aqp.core.domain.instrument import (
    BettingInstrument,
    Bond,
    Cfd,
    Commodity,
    CryptoPerpetual,
    CurrencyPair,
    ETF,
    Equity,
    FuturesContract,
    IndexInstrument,
    OptionContract,
    SyntheticInstrument,
    TokenizedAsset,
    instrument_class_for,
)
from aqp.core.domain.money import currency_of


def _id(sym: str, venue: str = "NASDAQ") -> InstrumentId:
    return InstrumentId(Symbol2(sym), Venue(venue))


def test_equity_basic():
    eq = Equity(
        instrument_id=_id("AAPL"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.SPOT,
        name="Apple Inc",
        cik="0000320193",
        isin="US0378331005",
        country="USA",
    )
    assert eq.symbol == "AAPL"
    assert eq.venue == "NASDAQ"
    assert eq.vt_symbol == "AAPL.NASDAQ"
    assert eq.cik == "0000320193"
    assert eq.product().value == "SPOT"


def test_etf_basic():
    etf = ETF(
        instrument_id=_id("SPY", "ARCA"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.ETF,
        name="SPDR S&P 500",
        underlying_index="S&P 500",
        expense_ratio=Decimal("0.0009"),
    )
    assert etf.product().value == "ETF"
    assert etf.underlying_index == "S&P 500"


def test_bond_basic():
    b = Bond(
        instrument_id=_id("UST10Y", "LOCAL"),
        asset_class=AssetClass.RATES,
        instrument_class=InstrumentClass.BOND,
        coupon=Decimal("0.045"),
        maturity=date(2035, 6, 30),
        face_value=Decimal("1000"),
        rating_sp="AA+",
        bond_class="government",
    )
    assert b.product().value == "BOND"
    assert b.rating_sp == "AA+"


def test_futures_contract():
    f = FuturesContract(
        instrument_id=_id("ESZ26", "CME"),
        asset_class=AssetClass.COMMODITY,
        instrument_class=InstrumentClass.FUTURE,
        underlying="ES",
        expiry=date(2026, 12, 18),
        contract_size=Decimal("50"),
        settlement_type=SettlementType.CASH,
    )
    assert f.product().value == "FUTURES"
    assert f.expiry == date(2026, 12, 18)


def test_option_contract():
    o = OptionContract(
        instrument_id=_id("AAPL_260618_C200", "CBOE"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.OPTION,
        underlying="AAPL",
        strike=Decimal("200"),
        expiry=date(2026, 6, 18),
        kind=OptionKind.CALL,
        style=OptionStyle.AMERICAN,
    )
    assert o.kind == OptionKind.CALL
    assert o.product().value == "OPTION"


def test_currency_pair():
    fx = CurrencyPair(
        instrument_id=_id("EURUSD", "IDEALPRO"),
        asset_class=AssetClass.FX,
        instrument_class=InstrumentClass.SPOT,
        base_currency=currency_of("EUR"),
        quote_currency=currency_of("USD"),
        pip_size=Decimal("0.0001"),
    )
    assert fx.base_currency.code == "EUR"
    assert fx.quote_currency.code == "USD"
    assert fx.product().value == "FOREX"


def test_crypto_perpetual():
    cp = CryptoPerpetual(
        instrument_id=_id("BTCUSDT", "BINANCE"),
        asset_class=AssetClass.CRYPTO,
        instrument_class=InstrumentClass.PERPETUAL,
        underlying="BTC",
        settlement_currency=currency_of("USDT"),
        funding_interval="8h",
        max_leverage=Decimal("125"),
    )
    assert cp.funding_interval == "8h"
    assert cp.settlement_currency.code == "USDT"


def test_betting_instrument():
    bi = BettingInstrument(
        instrument_id=_id("TRUMP2024", "POLYMARKET"),
        asset_class=AssetClass.EVENT,
        instrument_class=InstrumentClass.BETTING,
        event_name="2024 US Presidential Election",
        market_name="Will Trump win?",
        selection_name="YES",
    )
    assert bi.product().value == "BETTING"


def test_synthetic_instrument():
    s = SyntheticInstrument(
        instrument_id=_id("SPY_QQQ_LONG_SHORT", "LOCAL"),
        asset_class=AssetClass.MIXED,
        instrument_class=InstrumentClass.SYNTHETIC,
        legs=[_id("SPY", "ARCA"), _id("QQQ", "NASDAQ")],
        leg_weights={"SPY": Decimal("1"), "QQQ": Decimal("-1")},
    )
    assert len(s.legs) == 2


def test_tokenized_asset():
    ta = TokenizedAsset(
        instrument_id=_id("BAYC1234", "OPENSEA"),
        asset_class=AssetClass.CRYPTO,
        instrument_class=InstrumentClass.NFT,
        chain="ethereum",
        contract_address="0xbc4ca...",
        token_standard="ERC-721",
    )
    assert ta.token_standard == "ERC-721"


def test_cfd():
    c = Cfd(
        instrument_id=_id("SPX_CFD", "LOCAL"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.CFD,
        underlying="SPX",
        margin_rate=Decimal("0.05"),
    )
    assert c.product().value == "CFD"


def test_index_instrument():
    idx = IndexInstrument(
        instrument_id=_id("SPX", "LOCAL"),
        asset_class=AssetClass.INDEX,
        instrument_class=InstrumentClass.INDEX,
        administrator="S&P Dow Jones",
        constituent_count=500,
    )
    assert idx.product().value == "INDEX"


def test_commodity():
    c = Commodity(
        instrument_id=_id("GOLD_SPOT", "LBMA"),
        asset_class=AssetClass.COMMODITY,
        instrument_class=InstrumentClass.SPOT,
        grade="LBMA Good Delivery",
        unit_of_measure="troy_ounce",
    )
    assert c.unit_of_measure == "troy_ounce"


def test_dispatch_registry_returns_concrete_classes():
    assert instrument_class_for(AssetClass.EQUITY, InstrumentClass.SPOT) is Equity
    assert instrument_class_for(AssetClass.EQUITY, InstrumentClass.OPTION) is OptionContract
    assert instrument_class_for(AssetClass.EQUITY, InstrumentClass.ETF) is ETF
    assert instrument_class_for(AssetClass.RATES, InstrumentClass.BOND) is Bond
    assert instrument_class_for(AssetClass.CRYPTO, InstrumentClass.PERPETUAL) is CryptoPerpetual
    assert instrument_class_for(AssetClass.EVENT, InstrumentClass.BETTING) is BettingInstrument
    assert instrument_class_for(AssetClass.FX, InstrumentClass.SPOT) is CurrencyPair
    assert instrument_class_for("equity", "cfd") is Cfd


def test_dispatch_returns_none_for_unknown_pairs():
    assert instrument_class_for(AssetClass.ALTERNATIVE, InstrumentClass.MONEY_MARKET) is None


def test_equity_exposes_vt_symbol():
    eq = Equity(
        instrument_id=_id("TSLA"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.SPOT,
    )
    assert eq.vt_symbol == "TSLA.NASDAQ"
