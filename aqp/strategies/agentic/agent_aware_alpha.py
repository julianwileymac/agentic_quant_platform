"""Worked example: an alpha that consults an agent on every bar.

This is the canonical pattern for strategies that need true async agent
dispatch. It runs on the :class:`EventDrivenBacktester` (per-bar Python),
which is required because vbt-pro's per-bar callbacks are Numba-jit only.

The alpha computes a momentum prior locally, then consults a named agent
spec at every bar to **veto or confirm** the local signal. When the agent
endorses the prior with sufficient confidence, the alpha emits a signal;
otherwise it stays flat.

Use this as a template — copy and adapt to your own agent spec / prior.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


@register("AgentAwareMomentumAlpha", kind="alpha")
class AgentAwareMomentumAlpha(IAlphaModel):
    """Momentum alpha that consults an agent before each emission.

    Parameters
    ----------
    spec_name:
        Name of the registered :class:`AgentSpec` to consult.
    lookback_bars:
        Window size for the momentum prior.
    momentum_threshold:
        Absolute return threshold above which the local prior fires.
    min_agent_confidence:
        Floor on the agent's reported confidence; below this the alpha
        stays flat regardless of the prior.
    consult_ttl:
        TTL for the dispatcher cache. Most strategies want at least 1
        bar's worth so multiple symbols sharing context don't all hit the
        agent simultaneously.
    """

    def __init__(
        self,
        spec_name: str = "trader.signal_emitter",
        *,
        lookback_bars: int = 20,
        momentum_threshold: float = 0.02,
        min_agent_confidence: float = 0.6,
        consult_ttl: timedelta | float = timedelta(hours=1),
    ) -> None:
        self.spec_name = spec_name
        self.lookback_bars = int(lookback_bars)
        self.momentum_threshold = float(momentum_threshold)
        self.min_agent_confidence = float(min_agent_confidence)
        self.consult_ttl = consult_ttl
        self.stats: dict[str, int] = {
            "bars": 0,
            "prior_long": 0,
            "prior_short": 0,
            "agent_confirmed": 0,
            "agent_vetoed": 0,
            "agent_unavailable": 0,
        }

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        ts = context.get("current_time")
        dispatcher = context.get("agents")
        signals: list[Signal] = []
        if ts is None or bars.empty:
            return signals

        for sym in universe:
            self.stats["bars"] += 1
            prior, raw_return = self._momentum_prior(bars, sym.vt_symbol)
            if prior is None:
                continue
            if prior == Direction.LONG:
                self.stats["prior_long"] += 1
            else:
                self.stats["prior_short"] += 1

            if dispatcher is None:
                self.stats["agent_unavailable"] += 1
                signals.append(self._signal(sym, ts, prior, raw_return))
                continue

            inputs = {
                "vt_symbol": sym.vt_symbol,
                "as_of": str(ts),
                "prior_direction": prior.value,
                "prior_return": float(raw_return),
                "lookback": self.lookback_bars,
            }
            agent_result = dispatcher.consult(self.spec_name, inputs, ttl=self.consult_ttl)
            decision = self._extract_decision(agent_result)
            if decision is None:
                self.stats["agent_unavailable"] += 1
                signals.append(self._signal(sym, ts, prior, raw_return))
                continue

            if self._endorses(decision, prior):
                self.stats["agent_confirmed"] += 1
                signals.append(
                    self._signal(
                        sym,
                        ts,
                        prior,
                        raw_return,
                        confidence=float(decision.get("confidence", 1.0)),
                        rationale=str(decision.get("rationale") or ""),
                    )
                )
            else:
                self.stats["agent_vetoed"] += 1
        return signals

    def _momentum_prior(
        self, bars: pd.DataFrame, vt_symbol: str
    ) -> tuple[Direction | None, float]:
        sub = bars[bars["vt_symbol"] == vt_symbol].sort_values("timestamp")
        if len(sub) < self.lookback_bars + 1:
            return None, 0.0
        closes = sub["close"].astype(float).values
        recent = float(closes[-1])
        past = float(closes[-self.lookback_bars - 1])
        if past == 0:
            return None, 0.0
        ret = (recent - past) / past
        if ret > self.momentum_threshold:
            return Direction.LONG, ret
        if ret < -self.momentum_threshold:
            return Direction.SHORT, ret
        return None, ret

    @staticmethod
    def _extract_decision(result: Any) -> dict[str, Any] | None:
        if result is None:
            return None
        output = getattr(result, "output", result)
        if isinstance(output, dict):
            return output
        return None

    @staticmethod
    def _endorses(decision: dict[str, Any], prior: Direction) -> bool:
        action = str(decision.get("action") or decision.get("decision") or "").upper()
        if prior == Direction.LONG:
            return action in {"BUY", "LONG", "CONFIRM"}
        if prior == Direction.SHORT:
            return action in {"SELL", "SHORT", "CONFIRM"}
        return False

    def _signal(
        self,
        sym: Symbol,
        ts: Any,
        direction: Direction,
        raw_return: float,
        *,
        confidence: float = 0.7,
        rationale: str = "momentum prior endorsed",
    ) -> Signal:
        return Signal(
            symbol=sym,
            strength=min(1.0, abs(float(raw_return)) / max(self.momentum_threshold, 1e-9)),
            direction=direction,
            timestamp=ts,
            confidence=float(confidence),
            horizon_days=5,
            source=f"AgentAwareMomentumAlpha[{self.spec_name}]",
            rationale=rationale or None,
        )


__all__ = ["AgentAwareMomentumAlpha"]
