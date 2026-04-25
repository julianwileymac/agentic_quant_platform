"""Reference strategy examples ported from third-party libraries.

These wrappers expose backtesting.py / stock-analysis-engine demo strategies
as :class:`aqp.core.interfaces.IAlphaModel` implementations so they plug
straight into the 5-stage Framework and all three engines.
"""
from aqp.strategies.examples.sma4_cross import Sma4Cross
from aqp.strategies.examples.sma_cross import SmaCross
from aqp.strategies.examples.trailing_atr import TrailingATRAlpha

__all__ = ["Sma4Cross", "SmaCross", "TrailingATRAlpha"]
