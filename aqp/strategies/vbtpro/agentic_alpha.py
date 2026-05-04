"""Agent-driven alpha tuned for the vbt-pro engine.

Two complementary paths:

- **Precompute / panel mode** — :meth:`generate_panel_signals` is called
  once with the full bars frame. It batch-invokes the agent runtime (or
  reads from :class:`DecisionCache`) for every ``(vt_symbol, timestamp)``
  pair and renders the resulting decisions to wide entries / exits / size
  DataFrames. This is what :class:`aqp.backtest.vbtpro.engine.VectorbtProEngine`
  uses by default — fastest, fully deterministic, mirrors the existing
  ``run_agentic_backtest`` Celery task.
- **Per-window mode** — :class:`aqp.backtest.vbtpro.wfo.WalkForwardHarness`
  re-instantiates a fresh ``AgenticVbtAlpha`` per WFO window. The
  ``on_window_train`` hook (or the alpha's own ``warm`` method) lets you
  refresh prompts / feed the agent the train slice's news context before
  the test backtest runs.

The classic per-bar :meth:`generate_signals` path is preserved so this alpha
also drops into the event-driven engine and inherits the existing
:class:`aqp.strategies.agentic.agentic_alpha.AgenticAlpha` semantics for
HOLD-skipping and rating-based sizing.
"""
from __future__ import annotations

import logging
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import pandas as pd

from aqp.agents.trading.decision_cache import DecisionCache
from aqp.agents.trading.types import AgentDecision, TraderAction
from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

if TYPE_CHECKING:
    from aqp.backtest.vbtpro.signal_builder import SignalArrays

logger = logging.getLogger(__name__)


class AgenticVbtMode(StrEnum):
    PRECOMPUTE = "precompute"
    PER_WINDOW = "per_window"
    LIVE = "live"


_ACTION_TO_DIRECTION = {
    TraderAction.BUY: Direction.LONG,
    TraderAction.SELL: Direction.SHORT,
}


@register("AgenticVbtAlpha", kind="alpha")
class AgenticVbtAlpha(IAlphaModel):
    """Agent-driven alpha optimised for the vbt-pro engine.

    Parameters
    ----------
    spec_name:
        Name of the :class:`AgentSpec` to dispatch through
        :class:`aqp.agents.runtime.AgentRuntime`. Required only for
        ``live`` / ``per_window`` modes; ignored in pure ``precompute``
        mode (which reads the cache only).
    strategy_id:
        Logical id used to partition the :class:`DecisionCache`.
    cache_root:
        Optional override for the cache root directory.
    mode:
        See :class:`AgenticVbtMode`.
    min_confidence:
        Skip cached decisions whose confidence is below this threshold.
    rating_size_map:
        Optional mapping from the 5-tier rating to a target ``size_pct``.
    use_size_in_signals:
        When True, populates ``SignalArrays.size`` so vbt-pro sizes
        positions according to ``decision.size_pct``. When False,
        positions are sized via the engine's ``size`` / ``size_type``
        defaults.
    """

    def __init__(
        self,
        spec_name: str | None = None,
        *,
        strategy_id: str = "default",
        cache_root: str | None = None,
        mode: str | AgenticVbtMode = AgenticVbtMode.PRECOMPUTE,
        min_confidence: float = 0.0,
        rating_size_map: dict[str, float] | None = None,
        use_size_in_signals: bool = True,
        prompt_template: str | None = None,
        runtime_inputs_extra: dict[str, Any] | None = None,
    ) -> None:
        self.spec_name = spec_name
        self.strategy_id = strategy_id
        self.cache = DecisionCache(root=cache_root, strategy_id=strategy_id)
        self.mode = AgenticVbtMode(str(mode))
        self.min_confidence = float(min_confidence)
        self.rating_size_map = {
            str(k): float(v) for k, v in (rating_size_map or {}).items()
        }
        self.use_size_in_signals = bool(use_size_in_signals)
        self.prompt_template = prompt_template or (
            "Return a JSON trading decision for {vt_symbol} at {timestamp}: "
            "action BUY/SELL/HOLD, size_pct, confidence, rating, rationale."
        )
        self.runtime_inputs_extra = dict(runtime_inputs_extra or {})

        self.stats: dict[str, int] = {
            "bars": 0,
            "hits": 0,
            "misses": 0,
            "live_calls": 0,
            "hold_skips": 0,
            "low_confidence_skips": 0,
        }

    # ------------------------------------------------------------------
    # Panel path — used by the vbt-pro engine
    # ------------------------------------------------------------------

    def generate_panel_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any] | None = None,
    ) -> SignalArrays:
        """Panel-wide signal generation. Called by the vbt-pro engine."""
        from aqp.backtest.vbtpro.signal_builder import SignalArrays

        ctx = context or {}
        close: pd.DataFrame | None = ctx.get("close")
        if close is None:
            close = (
                bars.copy()
                .assign(timestamp=lambda df: pd.to_datetime(df["timestamp"]))
                .pivot_table(
                    index="timestamp",
                    columns="vt_symbol",
                    values="close",
                    aggfunc="last",
                )
                .sort_index()
                .ffill()
            )

        index = close.index
        cols = close.columns

        entries = pd.DataFrame(False, index=index, columns=cols)
        exits = pd.DataFrame(False, index=index, columns=cols)
        short_entries = pd.DataFrame(False, index=index, columns=cols)
        short_exits = pd.DataFrame(False, index=index, columns=cols)
        size = pd.DataFrame(0.0, index=index, columns=cols) if self.use_size_in_signals else None
        records: list[dict[str, Any]] = []

        symbols_by_vt = {s.vt_symbol: s for s in universe}

        for vt_symbol in cols:
            state: Direction | None = None
            for ts in index:
                self.stats["bars"] += 1
                decision = self._decision_for(vt_symbol, ts.to_pydatetime())
                if decision is None:
                    self.stats["misses"] += 1
                    continue
                self.stats["hits"] += 1

                target_dir, target_size = self._action_to_direction_size(decision)
                if target_dir is None:
                    self.stats["hold_skips"] += 1
                    continue

                if target_dir == Direction.LONG and state != Direction.LONG:
                    entries.at[ts, vt_symbol] = True
                    if state == Direction.SHORT:
                        short_exits.at[ts, vt_symbol] = True
                    state = Direction.LONG
                    if size is not None:
                        size.at[ts, vt_symbol] = target_size
                elif target_dir == Direction.SHORT and state != Direction.SHORT:
                    short_entries.at[ts, vt_symbol] = True
                    if state == Direction.LONG:
                        exits.at[ts, vt_symbol] = True
                    state = Direction.SHORT
                    if size is not None:
                        size.at[ts, vt_symbol] = -target_size

                records.append(
                    {
                        "timestamp": ts,
                        "vt_symbol": vt_symbol,
                        "direction": target_dir.value,
                        "strength": float(target_size),
                        "confidence": float(decision.confidence),
                        "horizon_days": int(
                            decision.trader_plan.horizon_days
                            if getattr(decision, "trader_plan", None)
                            else 5
                        ),
                        "source": f"AgenticVbtAlpha({self.strategy_id})",
                    }
                )

        return SignalArrays(
            entries=entries,
            exits=exits,
            short_entries=short_entries,
            short_exits=short_exits,
            size=size,
            signal_records=records,
        )

    # ------------------------------------------------------------------
    # IAlphaModel — per-bar path (event-driven engine compat)
    # ------------------------------------------------------------------

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        ts = context.get("current_time") or context.get("timestamp")
        if ts is None:
            if not bars.empty and "timestamp" in bars:
                ts = bars["timestamp"].iloc[-1]
            else:
                return []
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()

        signals: list[Signal] = []
        for sym in universe:
            self.stats["bars"] += 1
            decision = self._decision_for(sym.vt_symbol, ts)
            if decision is None:
                self.stats["misses"] += 1
                continue
            self.stats["hits"] += 1
            sig = self._to_signal(sym, decision, ts)
            if sig is not None:
                signals.append(sig)
        return signals

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _decision_for(self, vt_symbol: str, ts: datetime) -> AgentDecision | None:
        cached = self.cache.get(vt_symbol, ts)
        if cached is not None:
            return cached
        if self.mode == AgenticVbtMode.PRECOMPUTE:
            return None
        if self.mode in (AgenticVbtMode.LIVE, AgenticVbtMode.PER_WINDOW):
            return self._run_live(vt_symbol, ts)
        return None

    def _run_live(self, vt_symbol: str, ts: datetime) -> AgentDecision | None:
        if not self.spec_name:
            return None
        try:
            from aqp.agents.runtime import runtime_for
            from aqp.strategies.agentic.decision_provider import _decision_from_payload
        except Exception:
            return None

        prompt = self.prompt_template.format(vt_symbol=vt_symbol, timestamp=ts)
        try:
            result = runtime_for(self.spec_name).run(
                {
                    "prompt": prompt,
                    "vt_symbol": vt_symbol,
                    "timestamp": ts.isoformat(),
                    **self.runtime_inputs_extra,
                }
            )
        except Exception:
            logger.exception("AgentRuntime.run failed for %s @ %s", vt_symbol, ts)
            return None
        self.stats["live_calls"] += 1
        decision = _decision_from_payload(
            getattr(result, "output", result),
            vt_symbol=vt_symbol,
            timestamp=ts,
            provider=f"agent:{self.spec_name}",
        )
        if decision is not None:
            self.cache.put(decision)
        return decision

    def _action_to_direction_size(
        self, decision: AgentDecision
    ) -> tuple[Direction | None, float]:
        if decision.action == TraderAction.HOLD:
            return None, 0.0
        if decision.confidence < self.min_confidence:
            self.stats["low_confidence_skips"] += 1
            return None, 0.0
        size = float(decision.size_pct)
        if self.rating_size_map:
            rating_key = decision.rating.value
            numeric_key = str(
                {
                    "strong_buy": 2,
                    "buy": 1,
                    "hold": 0,
                    "sell": -1,
                    "strong_sell": -2,
                }.get(rating_key, 0)
            )
            size = float(
                self.rating_size_map.get(rating_key)
                or self.rating_size_map.get(numeric_key)
                or size
            )
        size = max(0.0, min(1.0, size))
        if size <= 0.0:
            return None, 0.0
        direction = _ACTION_TO_DIRECTION.get(decision.action)
        return direction, size

    def _to_signal(
        self,
        sym: Symbol,
        decision: AgentDecision,
        ts: Any,
    ) -> Signal | None:
        direction, size = self._action_to_direction_size(decision)
        if direction is None:
            return None
        return Signal(
            symbol=sym,
            strength=size,
            direction=direction,
            timestamp=ts,
            confidence=float(decision.confidence),
            horizon_days=int(
                decision.trader_plan.horizon_days
                if getattr(decision, "trader_plan", None)
                else 5
            ),
            source=f"AgenticVbtAlpha({self.strategy_id})",
            rationale=decision.rationale or None,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def hit_rate(self) -> float:
        hits = self.stats["hits"]
        misses = self.stats["misses"]
        denom = hits + misses
        return hits / denom if denom else 0.0


__all__ = ["AgenticVbtAlpha", "AgenticVbtMode"]
