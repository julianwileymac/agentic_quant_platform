"""Normalization strategies (Strategy pattern).

Codifies the **Strategy pattern** for the AQP Silver-layer transform:
each asset class / data domain ships a concrete
:class:`BaseNormalizationStrategy` subclass that knows how to coerce
provider-specific Bronze rows into the canonical Silver schema.

Concrete strategies:

- :class:`EquityNormalization` — bars + technicals
- :class:`OptionsNormalization` — chains + greeks
- :class:`MacroNormalization` — economic series + observations
- :class:`RegulatoryNormalization` — CFPB / FDA / USPTO
- :class:`NewsNormalization` — articles + sentiment
- :class:`MicrostructureNormalization` — order book / tick data

Add a new domain by subclassing :class:`BaseNormalizationStrategy`
and decorating with :func:`register_normalization_strategy`. The
``Silver`` transform node uses the registry to dispatch on data
domain so adding a new asset class never requires touching the engine
plumbing.
"""
from __future__ import annotations

from aqp.data.normalization.base import (
    BaseNormalizationStrategy,
    NormalizationResult,
    get_normalization_strategy,
    list_normalization_strategies,
    register_normalization_strategy,
)
from aqp.data.normalization.strategies import (
    EquityNormalization,
    MacroNormalization,
    MicrostructureNormalization,
    NewsNormalization,
    OptionsNormalization,
    RegulatoryNormalization,
)

__all__ = [
    "BaseNormalizationStrategy",
    "EquityNormalization",
    "MacroNormalization",
    "MicrostructureNormalization",
    "NewsNormalization",
    "NormalizationResult",
    "OptionsNormalization",
    "RegulatoryNormalization",
    "get_normalization_strategy",
    "list_normalization_strategies",
    "register_normalization_strategy",
]
