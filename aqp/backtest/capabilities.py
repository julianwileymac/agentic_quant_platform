"""Engine capability declarations.

Every backtest engine in AQP declares a frozen :class:`EngineCapabilities`
instance on its class body. The fallback engine inspects these to skip
incompatible engines (e.g. an LOB-only strategy on a bar-only engine) and
the ``engine_capabilities`` agent tool surfaces them to LLM agents.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineCapabilities:
    """Declarative feature surface for a backtest engine.

    Every concrete engine subclass declares one of these as a class attribute.
    The :class:`aqp.backtest.fallback_engine.FallbackBacktestEngine` consults
    the registry to skip engines that lack required capabilities (e.g. an
    options strategy will not be routed to an engine where ``supports_options``
    is False), and the ``engine_capabilities`` agent tool lets LLM-driven
    research crews inspect what each engine can do before dispatching work.
    """

    name: str
    description: str = ""

    # Input shapes
    supports_signals: bool = False
    supports_orders: bool = False
    supports_callbacks: bool = False
    supports_holding_baseline: bool = False
    supports_random_baseline: bool = False

    # Universe shapes
    supports_multi_asset: bool = False
    supports_single_asset_only: bool = False
    supports_cash_sharing: bool = False
    supports_grouping: bool = False

    # Order types / market features
    supports_short_selling: bool = False
    supports_leverage: bool = False
    supports_stops: bool = False
    supports_limit_orders: bool = False
    supports_options: bool = False
    supports_futures: bool = False
    supports_multiplier: bool = False
    supports_lob: bool = False

    # Execution model
    supports_async: bool = False
    supports_event_driven: bool = False
    supports_vectorized: bool = False
    supports_per_bar_python: bool = False

    # Research features
    supports_param_sweep: bool = False
    supports_walk_forward: bool = False
    supports_optimizer: bool = False
    supports_indicator_factory: bool = False
    supports_monte_carlo: bool = False
    supports_interrupts: bool = False

    # Data sources / venues
    us_market_data: bool = True
    cn_market_data: bool = False
    crypto_market_data: bool = False

    # Licensing / runtime
    license: str = ""
    requires_optional_dep: str | None = None
    notes: str = ""

    extras: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict, suitable for tool outputs."""
        return asdict(self)


__all__ = ["EngineCapabilities"]
