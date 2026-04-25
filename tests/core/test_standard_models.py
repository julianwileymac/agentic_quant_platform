"""Smoke tests that every ported OpenBB standard_model pair imports and instantiates."""
from __future__ import annotations

import importlib
import pkgutil

import pytest

import aqp.providers.standard_models as std_models
from aqp.providers.base import Data, QueryParams


def _iter_standard_model_modules():
    for info in pkgutil.iter_modules(std_models.__path__):
        if info.name == "__init__":
            continue
        yield importlib.import_module(f"{std_models.__name__}.{info.name}")


def test_every_module_imports():
    modules = list(_iter_standard_model_modules())
    # At minimum the 15 themed files we created.
    assert len(modules) >= 14


def test_every_module_has_paired_classes():
    for mod in _iter_standard_model_modules():
        qp_classes = [
            cls
            for name in dir(mod)
            if name.endswith("QueryParams")
            and isinstance((cls := getattr(mod, name)), type)
            and issubclass(cls, QueryParams)
        ]
        data_classes = [
            cls
            for name in dir(mod)
            if name.endswith("Data")
            and isinstance((cls := getattr(mod, name)), type)
            and issubclass(cls, Data)
        ]
        assert qp_classes, f"no QueryParams classes in {mod.__name__}"
        assert data_classes, f"no Data classes in {mod.__name__}"


def test_total_model_count_exceeds_60():
    total_qp = 0
    total_data = 0
    for mod in _iter_standard_model_modules():
        for name in dir(mod):
            cls = getattr(mod, name)
            if not isinstance(cls, type):
                continue
            if name.endswith("QueryParams") and issubclass(cls, QueryParams):
                total_qp += 1
            elif name.endswith("Data") and issubclass(cls, Data):
                total_data += 1
    assert total_qp >= 60, f"expected >=60 QueryParams, got {total_qp}"
    assert total_data >= 60, f"expected >=60 Data, got {total_data}"


def test_equity_info_roundtrip():
    from aqp.providers.standard_models.equity import (
        EquityInfoData,
        EquityInfoQueryParams,
    )

    qp = EquityInfoQueryParams(symbol="aapl")
    assert qp.symbol == "AAPL"  # field_validator uppercases

    data = EquityInfoData(
        symbol="AAPL",
        name="Apple Inc.",
        cik="0000320193",
        cusip="037833100",
        isin="US0378331005",
        lei="HWUPKR0MPOU8FGXBT394",
        employees=164_000,
    )
    assert data.symbol == "AAPL"
    assert data.employees == 164_000


def test_balance_sheet_data_roundtrip():
    from datetime import date
    from decimal import Decimal

    from aqp.providers.standard_models.fundamentals import (
        BalanceSheetData,
        BalanceSheetQueryParams,
    )

    qp = BalanceSheetQueryParams(symbol="msft", period="quarterly", limit=4)
    assert qp.symbol == "MSFT"

    d = BalanceSheetData(
        symbol="MSFT",
        period=date(2025, 12, 31),
        total_assets=Decimal("400_000_000"),
        total_equity=Decimal("200_000_000"),
    )
    assert d.total_assets == 400_000_000


def test_insider_trading_data_roundtrip():
    from datetime import date
    from decimal import Decimal

    from aqp.providers.standard_models.ownership import (
        InsiderTradingData,
        InsiderTradingQueryParams,
    )

    qp = InsiderTradingQueryParams(symbol="aapl", limit=50)
    assert qp.symbol == "AAPL"

    d = InsiderTradingData(
        symbol="AAPL",
        transaction_date=date(2025, 10, 1),
        owner_name="Tim Cook",
        transaction_type="Sale (S)",
        securities_transacted=Decimal("50_000"),
        transaction_price=Decimal("230"),
    )
    assert d.owner_name == "Tim Cook"


def test_treasury_rates_data():
    from datetime import date
    from decimal import Decimal

    from aqp.providers.standard_models.macro import (
        TreasuryRatesData,
        TreasuryRatesQueryParams,
    )

    qp = TreasuryRatesQueryParams(tenor="10y")
    assert qp.tenor == "10y"
    d = TreasuryRatesData(
        date=date(2026, 4, 1),
        tenor="10y",
        nominal_rate=Decimal("4.32"),
        real_rate=Decimal("1.8"),
    )
    assert d.tenor == "10y"


def test_options_chains_data():
    from datetime import date
    from decimal import Decimal

    from aqp.providers.standard_models.options import (
        OptionsChainsData,
        OptionsChainsQueryParams,
    )

    qp = OptionsChainsQueryParams(symbol="aapl")
    assert qp.symbol == "AAPL"

    d = OptionsChainsData(
        underlying_symbol="AAPL",
        contract_symbol="AAPL260618C00200000",
        expiry=date(2026, 6, 18),
        strike=Decimal("200"),
        option_type="call",
        bid=Decimal("18.5"),
        ask=Decimal("18.7"),
        implied_volatility=Decimal("0.24"),
    )
    assert d.strike == 200
