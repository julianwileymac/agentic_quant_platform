"""Legacy import path for the vbt-pro engine.

The full engine implementation moved to :mod:`aqp.backtest.vbtpro.engine`
when the deep vbt-pro integration landed (multi-mode dispatch, OHLC stops,
optimizer / orders / holding / random modes). This module is kept as a
delegate so YAML configs that reference
``module_path: aqp.backtest.vectorbtpro_engine`` continue to resolve the
new class.
"""
from __future__ import annotations

from aqp.backtest.vbtpro.engine import VALID_MODES, VectorbtProEngine

__all__ = ["VectorbtProEngine", "VALID_MODES"]
