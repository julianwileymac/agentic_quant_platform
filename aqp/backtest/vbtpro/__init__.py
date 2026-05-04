"""Deep vectorbt-pro integration.

This subpackage promotes vectorbt-pro to AQP's primary backtest engine.

The previous integration was a 10-line subclass of OSS vectorbt that only
handled signal-based alphas. This subpackage exposes the full vbt-pro
surface:

- ``engine.VectorbtProEngine`` — multi-mode engine: ``signals``, ``orders``,
  ``optimizer``, ``holding``, ``random`` (each routes to a different
  ``Portfolio.from_*`` constructor).
- ``signal_builder`` — converts AQP :class:`IAlphaModel` outputs into wide
  entries/exits/size DataFrames (with both per-bar and panel paths).
- ``order_builder`` — converts AQP :class:`IOrderModel` outputs into wide
  order arrays for ``Portfolio.from_orders``.
- ``optimizer_adapter`` — wraps ``vectorbtpro.portfolio.pfopt.PortfolioOptimizer``
  for the ``optimizer`` mode.
- ``wfo`` — :class:`WalkForwardHarness` built on ``Splitter`` /
  ``PurgedWalkForwardCV``; calls ``Splitter.apply`` so Python (and therefore
  agents/ML) runs per-window.
- ``param_sweep`` — wraps ``vectorbtpro.utils.params.Param`` for grid sweeps.
- ``indicator_factory_bridge`` — registers AQP indicator-zoo entries as vbt-pro
  ``IndicatorFactory`` indicators.
- ``result_mapper`` — converts vbt-pro ``Portfolio`` to AQP
  :class:`BacktestResult` with normalised summary keys.

**Numba constraint**: vbt-pro's per-bar callbacks (``signal_func_nb`` etc) are
JIT-only and cannot host LLM agents or Python ML calls. Agents and ML run in
**precompute** mode (decisions baked into wide arrays before simulation) or
**per-window** mode (Python in the loop via :meth:`WalkForwardHarness.run`).
"""
from __future__ import annotations

from aqp.backtest.vbtpro.engine import VectorbtProEngine  # noqa: F401
from aqp.backtest.vbtpro.result_mapper import portfolio_to_backtest_result  # noqa: F401
from aqp.backtest.vbtpro.signal_builder import SignalArrays, build_signal_arrays  # noqa: F401

__all__ = [
    "VectorbtProEngine",
    "SignalArrays",
    "build_signal_arrays",
    "portfolio_to_backtest_result",
]
