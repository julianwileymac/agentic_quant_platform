"""Tests for the Phase 1 (migration 0039) extended instrument taxonomy.

Covers REIT / MutualFund / OTCDerivative / ADR / GDR domain and ORM
shapes, plus the ``InstrumentMeasure`` registry.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from aqp.core.domain.enums import AssetClass, InstrumentClass, Product
from aqp.core.domain.identifiers import InstrumentId, Symbol2, Venue
from aqp.core.domain.instrument import (
    AmericanDepositaryReceipt,
    GlobalDepositaryReceipt,
    MutualFund,
    OTCDerivative,
    REIT,
    instrument_class_for,
)


def _id(sym: str, venue: str = "NYSE") -> InstrumentId:
    return InstrumentId(Symbol2(sym), Venue(venue))


# ---------------------------------------------------------------------------
# Domain registry dispatch — every new (asset_class, instrument_class) pair
# resolves to its concrete subclass.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "asset_class, instrument_class, expected",
    [
        (AssetClass.EQUITY, InstrumentClass.REIT, REIT),
        (AssetClass.EQUITY, InstrumentClass.MUTUAL_FUND, MutualFund),
        (AssetClass.MIXED, InstrumentClass.OTC_DERIVATIVE, OTCDerivative),
        (AssetClass.EQUITY, InstrumentClass.ADR, AmericanDepositaryReceipt),
        (AssetClass.EQUITY, InstrumentClass.GDR, GlobalDepositaryReceipt),
    ],
)
def test_registry_dispatches_new_taxonomy(asset_class, instrument_class, expected):
    """Every new pair from Phase 1 resolves to its concrete domain class."""
    cls = instrument_class_for(asset_class, instrument_class)
    assert cls is expected


def test_instrument_class_enum_values():
    """The new InstrumentClass enum values use the migration-canonical strings."""
    assert InstrumentClass.REIT.value == "reit"
    assert InstrumentClass.MUTUAL_FUND.value == "mutual_fund"
    assert InstrumentClass.OTC_DERIVATIVE.value == "otc_derivative"
    assert InstrumentClass.ADR.value == "adr"
    assert InstrumentClass.GDR.value == "gdr"


def test_product_enum_extends():
    """vnpy-parity Product enum carries the new shapes."""
    assert Product.REIT.value == "REIT"
    assert Product.OTC.value == "OTC"
    assert Product.ADR.value == "ADR"
    assert Product.GDR.value == "GDR"


# ---------------------------------------------------------------------------
# Domain construction — every subclass accepts its expected fields.
# ---------------------------------------------------------------------------


def test_reit_construction():
    reit = REIT(
        instrument_id=_id("PLD"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.REIT,
        name="Prologis Inc",
        reit_class="equity",
        property_sector="industrial",
        distribution_yield=Decimal("0.029"),
        ffo_per_share=Decimal("5.65"),
        payout_ratio=Decimal("0.70"),
        country="USA",
    )
    assert reit.symbol == "PLD"
    assert reit.product() is Product.REIT
    assert reit.reit_class == "equity"
    assert reit.property_sector == "industrial"
    assert reit.distribution_yield == Decimal("0.029")


def test_mutual_fund_construction():
    fund = MutualFund(
        instrument_id=_id("VFINX", "MUTF"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.MUTUAL_FUND,
        name="Vanguard 500 Index Fund Investor",
        fund_family="Vanguard",
        share_class="Investor",
        expense_ratio=Decimal("0.0014"),
        nav_currency="USD",
        minimum_investment=Decimal("3000"),
        fund_kind="open_end",
        benchmark_index="S&P 500",
        is_index_fund=True,
        is_actively_managed=False,
        distribution_frequency="quarterly",
    )
    assert fund.product() is Product.FUND
    assert fund.fund_family == "Vanguard"
    assert fund.is_index_fund is True
    assert fund.is_actively_managed is False
    assert fund.benchmark_index == "S&P 500"


def test_otc_derivative_swap():
    swap = OTCDerivative(
        instrument_id=_id("SWAP-USD-5Y-FIXED-FLOAT", "OTC"),
        asset_class=AssetClass.MIXED,
        instrument_class=InstrumentClass.OTC_DERIVATIVE,
        instrument_kind="swap",
        counterparty_lei="EXAMPLE0000000000000",
        isda_master_agreement_id="ISDA-2002-CSA-001",
        notional_currency="USD",
        notional_amount=Decimal("10000000"),
        settlement_currency="USD",
        trade_date=date(2026, 5, 16),
        effective_date=date(2026, 5, 18),
        termination_date=date(2031, 5, 18),
        payment_frequency="semi_annual",
        cleared=True,
        ccp_name="LCH SwapClear",
        legs=[
            {"pay_receive": "pay", "leg_type": "fixed", "fixed_rate": 0.035},
            {"pay_receive": "receive", "leg_type": "float", "rate_index": "SOFR"},
        ],
    )
    assert swap.product() is Product.OTC
    assert swap.instrument_kind == "swap"
    assert swap.cleared is True
    assert len(swap.legs) == 2
    assert swap.legs[0]["fixed_rate"] == 0.035


def test_adr_construction_and_underlying_link():
    adr = AmericanDepositaryReceipt(
        instrument_id=_id("BABA"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.ADR,
        name="Alibaba Group Holding ADR",
        underlying_instrument_id="9988-hkex-uuid",
        underlying_ticker="9988",
        underlying_venue="HKEX",
        underlying_isin="KYG017191142",
        conversion_ratio=Decimal("8"),
        depository_bank_name="Citibank N.A.",
        sponsorship_level="III",
        listing_venue="NYSE",
        home_country="China",
        isin="US01609W1027",
    )
    assert adr.product() is Product.ADR
    assert adr.conversion_ratio == Decimal("8")
    assert adr.sponsorship_level == "III"
    # Cross-market basis algorithm reads underlying_instrument_id + ratio
    # without any join.
    assert adr.underlying_instrument_id == "9988-hkex-uuid"


def test_gdr_construction_with_regulatory_regime():
    gdr = GlobalDepositaryReceipt(
        instrument_id=_id("GAZP", "LSE"),
        asset_class=AssetClass.EQUITY,
        instrument_class=InstrumentClass.GDR,
        name="Gazprom GDR",
        underlying_ticker="GAZP",
        underlying_venue="MOEX",
        conversion_ratio=Decimal("2"),
        depository_bank_name="Bank of New York Mellon",
        listing_venue="LSE",
        regulatory_regime="Reg_S_144A",
        home_country="Russia",
    )
    assert gdr.product() is Product.GDR
    assert gdr.regulatory_regime == "Reg_S_144A"
    assert gdr.conversion_ratio == Decimal("2")


# ---------------------------------------------------------------------------
# ORM shape — every new mapped class has the right polymorphic identity.
# ---------------------------------------------------------------------------


def test_orm_polymorphic_identities():
    from aqp.persistence.models_instruments import (
        InstrumentADR,
        InstrumentGDR,
        InstrumentMeasure,
        InstrumentMutualFund,
        InstrumentOTCDerivative,
        InstrumentREIT,
    )

    assert InstrumentREIT.__mapper_args__["polymorphic_identity"] == "reit"
    assert InstrumentMutualFund.__mapper_args__["polymorphic_identity"] == "mutual_fund"
    assert (
        InstrumentOTCDerivative.__mapper_args__["polymorphic_identity"]
        == "otc_derivative"
    )
    assert InstrumentADR.__mapper_args__["polymorphic_identity"] == "adr"
    assert InstrumentGDR.__mapper_args__["polymorphic_identity"] == "gdr"
    # InstrumentMeasure is NOT a subclass of Instrument -- it's a standalone
    # registry row. Make sure it has its own table.
    assert InstrumentMeasure.__tablename__ == "instrument_measures"


def test_orm_tables_present_in_metadata():
    from aqp.persistence import Base

    table_names = set(Base.metadata.tables.keys())
    for expected in (
        "instrument_reit",
        "instrument_mutual_fund",
        "instrument_otc_derivative",
        "instrument_adr",
        "instrument_gdr",
        "instrument_measures",
    ):
        assert expected in table_names, f"missing table: {expected}"


def test_instrument_measure_unique_constraint():
    """Composite uniqueness is keyed by (instrument_id, measure_type, frequency, dataset_field)."""
    from aqp.persistence.models_instruments import InstrumentMeasure

    constraints = {
        c.name
        for c in InstrumentMeasure.__table__.constraints
        if c.name is not None
    }
    assert "uq_instrument_measures_address" in constraints


def test_adr_has_two_fk_to_instruments():
    """ADR row has both a self FK (joined-table) and an FK to the underlying."""
    from aqp.persistence.models_instruments import InstrumentADR

    fk_targets = {
        list(fk.column.table.name for fk in col.foreign_keys)
        for col in InstrumentADR.__table__.columns
        if col.foreign_keys
    }
    # Flatten and check both `id` (self FK) and `underlying_instrument_id`
    # point at instruments table.
    all_targets = [t for sublist in fk_targets for t in sublist]
    assert all_targets.count("instruments") >= 2
