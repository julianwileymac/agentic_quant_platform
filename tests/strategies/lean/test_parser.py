"""Tests for :mod:`aqp.strategies.lean.parser`."""
from __future__ import annotations

import importlib
import textwrap

# Import the parser directly rather than through ``aqp.strategies`` so the
# pre-existing broken re-exports in that package's __init__ don't affect
# test collection.
parse_lean_source = importlib.import_module(
    "aqp.strategies.lean.parser"
).parse_lean_source


MACD_TEMPLATE = textwrap.dedent('''
    from AlgorithmImports import *


    class MACDTrendAlgorithm(QCAlgorithm):
        """Trades SPY on MACD crossovers — LEAN's canonical momentum example."""

        def Initialize(self):
            self.SetStartDate(2015, 1, 1)
            self.SetEndDate(2017, 12, 31)
            self.SetCash(100000)
            self.AddEquity("SPY", Resolution.Daily)
            self.macd = self.MACD("SPY", 12, 26, 9, MovingAverageType.Exponential, Resolution.Daily)

        def OnData(self, data):
            if not self.macd.IsReady:
                return
            holdings = self.Portfolio["SPY"].Quantity
            signal = (self.macd.Current.Value - self.macd.Signal.Current.Value) / self.macd.Fast.Current.Value
            if holdings <= 0 and signal > 0.001:
                self.SetHoldings("SPY", 1.0)
            elif holdings >= 0 and signal < -0.001:
                self.Liquidate("SPY")
''')


OPTIONS_TEMPLATE = textwrap.dedent('''
    from AlgorithmImports import *


    class LongAndShortButterflyCallStrategiesAlgorithm(QCAlgorithm):
        """Multi-leg butterfly call strategy on SPY weekly options."""

        def Initialize(self):
            self.SetStartDate(2020, 1, 1)
            self.AddOption("SPY")

        def OnData(self, slice):
            chain = slice.OptionChains.get(self.option_symbol)
            if chain is None:
                return
            strategy = OptionStrategies.butterfly_call(self.option_symbol, 100, 105, 110, datetime(2020,12,18))
            self.Buy(strategy, 1)
''')


def test_parses_macd_template() -> None:
    info = parse_lean_source(MACD_TEMPLATE, source_path="Algorithm.Python/MACDTrendAlgorithm.py")
    assert info is not None
    assert info.class_name == "MACDTrendAlgorithm"
    assert info.base_class == "QCAlgorithm"
    assert "MACD" in info.indicators
    assert "equities" in info.asset_classes
    assert "SPY" in info.universe_symbols
    assert "momentum" in info.tags


def test_parses_options_template() -> None:
    info = parse_lean_source(OPTIONS_TEMPLATE)
    assert info is not None
    assert info.class_name == "LongAndShortButterflyCallStrategiesAlgorithm"
    assert "options" in info.asset_classes
    assert "multi_leg" in info.tags


def test_returns_none_on_non_qcalgorithm_source() -> None:
    src = "class Helper:\n    pass\n"
    assert parse_lean_source(src) is None


def test_returns_none_on_syntax_error() -> None:
    src = "def broken(:\n    pass\n"
    assert parse_lean_source(src) is None


def test_metadata_dict_is_json_safe() -> None:
    info = parse_lean_source(MACD_TEMPLATE)
    assert info is not None
    meta = info.to_metadata_dict()
    import json

    json.dumps(meta)  # would raise if non-serialisable
