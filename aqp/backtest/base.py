"""Shared backtest engine contract.

:class:`BaseBacktestEngine` is the canonical ABC every backtest engine in
AQP inherits from. Engines declare their feature surface via
:class:`aqp.backtest.capabilities.EngineCapabilities` so the fallback
engine and the ``engine_capabilities`` agent tool can introspect and
select intelligently.

The previous codebase used pure duck-typing (any class with a ``run()``
method was an engine). This module formalises the contract without
breaking that history: existing engines simply inherit from this base,
their existing ``run`` implementations satisfy the abstract method, and
they gain the ``capabilities`` slot for the fallback cascade.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

import pandas as pd

from aqp.backtest.capabilities import EngineCapabilities

if TYPE_CHECKING:
    from aqp.backtest.engine import BacktestResult

logger = logging.getLogger(__name__)


class BaseBacktestEngine(ABC):
    """Common ABC for backtest engines.

    Every concrete engine (event-driven, vectorbt-pro, backtesting.py, ZVT,
    AAT, fallback cascade) implements :meth:`run` and declares its feature
    surface via :attr:`capabilities`. The class attribute is a frozen
    dataclass so it is safe to share across instances.
    """

    capabilities: ClassVar[EngineCapabilities] = EngineCapabilities(
        name="base",
        description="abstract base engine",
    )

    @abstractmethod
    def run(self, strategy: Any, bars: pd.DataFrame) -> BacktestResult:
        """Run a backtest and return a :class:`BacktestResult`.

        ``strategy`` may be an :class:`~aqp.core.interfaces.IAlphaModel` or
        :class:`~aqp.core.interfaces.IStrategy` (or anything duck-compatible
        with what the concrete engine consumes). ``bars`` is a tidy
        DataFrame with at minimum ``timestamp, vt_symbol, open, high, low,
        close, volume`` columns.
        """

    def describe(self) -> dict[str, Any]:
        """Return a JSON-friendly dict of this engine's capabilities."""
        return self.capabilities.to_dict()

    def supports(self, *flags: str) -> bool:
        """Convenience helper: ``engine.supports("signals", "multi_asset")``.

        Each flag is checked against ``capabilities.supports_<flag>`` and
        ``capabilities.<flag>`` (in that order). Returns ``True`` only if
        every flag resolves to a truthy attribute.
        """
        for flag in flags:
            attr = f"supports_{flag}" if not flag.startswith("supports_") else flag
            value = getattr(self.capabilities, attr, None)
            if value is None:
                value = getattr(self.capabilities, flag, None)
            if not value:
                return False
        return True


def engine_capabilities_index() -> dict[str, EngineCapabilities]:
    """Return the registry of capabilities for every importable AQP engine.

    Lazy-imports each engine module so missing optional dependencies do not
    crash the index. Used by :class:`aqp.backtest.fallback_engine` and the
    ``engine_capabilities`` agent tool.
    """
    import importlib

    targets: list[tuple[str, str]] = [
        ("EventDrivenBacktester", "aqp.backtest.engine"),
        ("VectorbtEngine", "aqp.backtest.vectorbt_engine"),
        ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
        ("BacktestingPyEngine", "aqp.backtest.bt_engine"),
        ("FallbackBacktestEngine", "aqp.backtest.fallback_engine"),
        ("ZvtBacktestEngine", "aqp.backtest.zvt_engine"),
        ("AatBacktestEngine", "aqp.backtest.aat_engine"),
    ]
    out: dict[str, EngineCapabilities] = {}
    for cls_name, mod_path in targets:
        try:
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name, None)
            if cls is not None and hasattr(cls, "capabilities"):
                out[cls_name] = cls.capabilities
        except Exception as exc:  # pragma: no cover - optional deps
            logger.debug("engine %s unavailable: %s", cls_name, exc)
    return out


__all__ = ["BaseBacktestEngine", "engine_capabilities_index"]
