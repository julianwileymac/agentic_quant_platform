"""Strategy-level warmup enforcement.

The classic look-ahead bias in event-driven backtests is a strategy
that emits signals before its indicators are primed. Each engine has
its own ``warmup_bars`` knob today, but those operate at the engine
level and don't see the strategy's actual indicator state. This
module elevates warmup into an explicit strategy contract:

- :class:`WarmupEnforcerMixin` declares ``warmup_period`` (in bars) on
  the strategy class.
- The engine asks the strategy whether it is ready *before* dispatching
  ``on_bar`` / ``on_data``. Strategies that pass the bar count gate go
  through; otherwise the engine still updates indicators (so the
  strategy can accumulate state) but suppresses every signal.
- Strategies can override :meth:`is_warmed_up` to add custom logic
  (e.g. "wait until at least one cross-sectional ADV is non-NULL"),
  but the default bar-count check covers 95% of cases.

The mixin is designed to compose with both :class:`IStrategy.on_bar`
and :class:`IStrategy.on_data` engine entry points without the
strategy author having to remember to short-circuit at the top of
their handler.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WarmupEnforcerMixin:
    """Mixin that gates signal emission until the warmup window passes.

    Usage:

    .. code-block:: python

        from aqp.backtest.warmup import WarmupEnforcerMixin
        from aqp.core.interfaces import IStrategy

        class MyMomentumStrategy(WarmupEnforcerMixin, IStrategy):
            warmup_period = 252  # one year of daily bars

            def on_bar(self, bar, ctx):
                if not self.is_warmed_up():
                    return []  # engine already short-circuits, this is belt-and-suspenders
                ...

    The mixin tracks ``_warmup_seen_bars`` automatically; the engine
    increments it via :meth:`note_bar_observed` on every dispatch. If
    your strategy already consumes ``ctx`` for some bookkeeping, you
    can also call :meth:`note_bar_observed` from your handler — the
    engine and the mixin both no-op when the counter is already past
    the warmup target.
    """

    #: Number of bars that must elapse before the strategy is
    #: considered primed. Override per strategy. Set to ``0`` to
    #: disable the gate (matches the legacy behaviour).
    warmup_period: int = 0

    _warmup_seen_bars: int = 0

    def note_bar_observed(self) -> None:
        """Engine hook — increment the seen-bar counter for warmup."""
        if int(self.warmup_period or 0) <= 0:
            return
        self._warmup_seen_bars += 1

    def is_warmed_up(self) -> bool:
        """Return True iff the strategy has observed enough bars to act.

        Override this for strategies that need richer readiness logic
        (e.g. cross-sectional indicators that depend on every symbol
        having a non-NULL value). Always combine the override with
        ``super().is_warmed_up()`` so the bar-count guard still
        applies.
        """
        target = int(self.warmup_period or 0)
        if target <= 0:
            return True
        return self._warmup_seen_bars >= target

    def warmup_progress(self) -> float:
        """Convenience: ``seen / target`` clamped to ``[0, 1]``."""
        target = int(self.warmup_period or 0)
        if target <= 0:
            return 1.0
        if self._warmup_seen_bars >= target:
            return 1.0
        return float(self._warmup_seen_bars) / float(target)


def strategy_is_warmed_up(strategy: Any) -> bool:
    """Return True if *strategy* is past its warmup window.

    Returns ``True`` for strategies that don't subclass
    :class:`WarmupEnforcerMixin` so the gate is opt-in. Engine
    integration code uses this helper to keep the warmup logic in one
    place.
    """
    is_ready = getattr(strategy, "is_warmed_up", None)
    if not callable(is_ready):
        return True
    try:
        return bool(is_ready())
    except Exception:  # noqa: BLE001
        logger.debug("strategy_is_warmed_up raised; defaulting to True", exc_info=True)
        return True


def note_bar(strategy: Any) -> None:
    """Engine hook — increment the per-strategy bar counter."""
    note = getattr(strategy, "note_bar_observed", None)
    if callable(note):
        try:
            note()
        except Exception:  # noqa: BLE001
            logger.debug("note_bar_observed raised; ignoring", exc_info=True)


__all__ = [
    "WarmupEnforcerMixin",
    "note_bar",
    "strategy_is_warmed_up",
]
