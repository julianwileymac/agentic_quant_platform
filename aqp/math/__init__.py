"""Quantitative finance math primitives.

Phase 4 (Alembic 0042+) ships :mod:`aqp.math.arbitrage` with the
statistical-arbitrage primitives the report calls out:

* Augmented Dickey-Fuller for unit-root testing
* Engle-Granger two-step cointegration
* Johansen multivariate cointegration
* Rolling z-score + Ornstein-Uhlenbeck half-life
* A-share <-> H-share cross-market basis
* ADR / GDR basis vs underlying
"""
from __future__ import annotations

__all__: list[str] = []
