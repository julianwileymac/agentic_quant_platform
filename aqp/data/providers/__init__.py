"""Optional data-provider ladders.

:mod:`aqp.data.ingestion` already provides concrete adapters for
yfinance, local CSVs, and local Parquet. This package sits on top:

- :mod:`aqp.data.providers.priority` — FinRL-Trading's FMP → WRDS →
  Yahoo priority ladder. Try each in turn and fall back silently so
  every call returns the best data available without the caller
  branching on which provider works today.
"""
from __future__ import annotations

from aqp.data.providers.priority import PriorityLadder, default_ladder

__all__ = ["PriorityLadder", "default_ladder"]
