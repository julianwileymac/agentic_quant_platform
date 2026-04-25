"""Paper/live trading engine — the Lean-style async runtime.

Re-exports the two entry points application code normally reaches for:

- :class:`aqp.trading.session.PaperTradingSession` — the async runtime.
- :func:`aqp.trading.runner.run_paper_session_from_config` — config-driven
  entry point used by both the Celery task and the ``aqp paper run`` CLI.
"""
from __future__ import annotations

from aqp.trading.clock import RealTimeClock, SimulatedReplayClock
from aqp.trading.runner import (
    PaperSessionResult,
    build_session_from_config,
    run_paper_session_from_config,
)
from aqp.trading.session import PaperSessionConfig, PaperTradingSession
from aqp.trading.state import PaperSessionState

__all__ = [
    "PaperSessionConfig",
    "PaperSessionResult",
    "PaperSessionState",
    "PaperTradingSession",
    "RealTimeClock",
    "SimulatedReplayClock",
    "build_session_from_config",
    "run_paper_session_from_config",
]
