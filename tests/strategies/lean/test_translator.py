"""Tests for :mod:`aqp.strategies.lean.translator`."""
from __future__ import annotations

import importlib
import textwrap

# Import the translator directly so the pre-existing broken re-exports
# in ``aqp.strategies.__init__`` don't break test collection.
translate_lean_to_framework = importlib.import_module(
    "aqp.strategies.lean.translator"
).translate_lean_to_framework


MACD_TEMPLATE = textwrap.dedent('''
    from AlgorithmImports import *


    class MACDTrendAlgorithm(QCAlgorithm):
        """MACD crossover example."""

        def Initialize(self):
            self.SetStartDate(2015, 1, 1)
            self.SetEndDate(2017, 12, 31)
            self.SetCash(100000)
            self.AddEquity("SPY", Resolution.Daily)
            self.macd = self.MACD("SPY", 12, 26, 9)

        def OnData(self, data):
            if self.macd.IsReady:
                self.SetHoldings("SPY", 0.5)
''')


def test_translator_rewrites_initialize_and_on_data() -> None:
    out = translate_lean_to_framework(MACD_TEMPLATE)
    assert "class MACDTrendAlgorithm(FrameworkAlgorithm)" in out
    assert "def prepare(" in out
    assert "def on_bar(" in out
    assert "@register('MACDTrendAlgorithm', kind='strategy', source='lean')" in out


def test_translator_rewrites_self_api_calls() -> None:
    out = translate_lean_to_framework(MACD_TEMPLATE)
    assert "ctx.add_equity('SPY'" in out
    assert "ctx.set_holdings('SPY'" in out


def test_translator_rewrites_indicators_to_aqp_namespace() -> None:
    out = translate_lean_to_framework(MACD_TEMPLATE)
    assert "aqp.data.indicators.MACD('SPY'" in out


def test_translator_captures_set_cash_and_dates() -> None:
    out = translate_lean_to_framework(MACD_TEMPLATE)
    assert "starting_cash" in out
    assert "100000" in out
    assert "start_date" in out
    assert "2015-01-01" in out


def test_translator_preserves_unparseable_source_as_comment() -> None:
    out = translate_lean_to_framework("def broken(:\n    pass\n")
    assert out.startswith("# Could not parse LEAN source")


def test_translator_handles_no_qcalgorithm() -> None:
    out = translate_lean_to_framework("class Helper:\n    pass\n")
    assert out.startswith("# No QCAlgorithm subclass found")
