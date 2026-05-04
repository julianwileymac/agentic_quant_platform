"""vbt-pro-tuned strategy components.

This subpackage holds AQP strategy components that integrate cleanly with the
vbt-pro engine's batch / panel-wide invocation model. They also work with
the event-driven engine (the panel path is opt-in via
``generate_panel_signals``; the legacy ``generate_signals`` path remains).

Components:

- :class:`AgenticVbtAlpha` — agent-driven alpha. Precompute mode bakes the
  full decision panel before simulation; per-window mode is wired by
  :class:`aqp.backtest.vbtpro.wfo.WalkForwardHarness`.
- :class:`MLVbtAlpha` — wraps any :class:`aqp.ml.base.Model` (including
  MLflow-loaded ones) and converts its predictions to entries/exits via
  thresholding, top-k, or sector-neutralisation.
- :class:`AgenticOrderModel` — implements :class:`aqp.core.interfaces.IOrderModel`
  so agent-emitted orders can drive the vbt-pro ``orders`` mode.

The classes are exported lazily so importing the package does not pull in
optional vbt-pro dependencies.
"""
from __future__ import annotations

from aqp.strategies.vbtpro.agent_order_model import AgenticOrderModel  # noqa: F401
from aqp.strategies.vbtpro.agentic_alpha import AgenticVbtAlpha  # noqa: F401
from aqp.strategies.vbtpro.ml_alpha import MLVbtAlpha  # noqa: F401

__all__ = [
    "AgenticOrderModel",
    "AgenticVbtAlpha",
    "MLVbtAlpha",
]
