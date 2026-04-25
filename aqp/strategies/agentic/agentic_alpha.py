"""``AgenticAlpha`` — turn LLM trader decisions into :class:`Signal` objects.

The glue between the TradingAgents-style trader crew and the platform's
Lean-style 5-stage backtest framework. Works in three modes:

- ``precompute`` (default): read decisions from a
  :class:`aqp.agents.trading.decision_cache.DecisionCache`; if no
  decision exists for ``(symbol, timestamp)``, emit nothing. This mode
  is the cheapest and is what the Celery ``run_agentic_backtest`` task
  uses after it runs ``precompute_decisions``.
- ``precompute_plus_audit``: same as ``precompute``, but a configurable
  fraction of bars are replayed live through the crew and the deltas
  are recorded. Lets users sanity-check a cache without paying for a
  full live run.
- ``live``: call the crew at every bar. Slow + expensive; only useful
  for small demos and fidelity checks.

The adapter from :class:`aqp.agents.trading.types.TraderAction` to
:class:`aqp.core.types.Direction`:

=================  ==========================  =========================
``TraderAction``   ``Direction``               ``Signal.strength``
=================  ==========================  =========================
``BUY``            ``LONG``                    ``size_pct``
``SELL``           ``SHORT``                   ``size_pct``
``HOLD``           (no signal emitted)         —
=================  ==========================  =========================
"""
from __future__ import annotations

import logging
import random
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.agents.trading.decision_cache import DecisionCache
from aqp.agents.trading.types import AgentDecision, TraderAction
from aqp.config import settings
from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


class AgenticAlphaMode(StrEnum):
    PRECOMPUTE = "precompute"
    PRECOMPUTE_PLUS_AUDIT = "precompute_plus_audit"
    LIVE = "live"


_ACTION_TO_DIRECTION = {
    TraderAction.BUY: Direction.LONG,
    TraderAction.SELL: Direction.SHORT,
}


@register("AgenticAlpha")
class AgenticAlpha(IAlphaModel):
    """Consume LLM trader decisions as alpha.

    Parameters
    ----------
    strategy_id:
        Logical id used to partition :class:`DecisionCache` files. Defaults
        to ``"default"`` so quickstart runs don't need to configure one.
    cache_root:
        Optional override for the cache root directory.
    mode:
        See :class:`AgenticAlphaMode`.
    audit_fraction:
        Probability (0-1) of replaying a bar through the live crew in
        ``precompute_plus_audit`` mode.
    min_confidence:
        Skip decisions below this confidence threshold (kept fluid so the
        wizard can expose it).
    rating_size_map:
        Optional mapping from the 5-tier rating to a target ``size_pct``.
        When provided, overrides the crew's own ``size_pct``. Keys may be
        either the enum value (``"strong_buy"``) or the signed integer
        (``2``, ``1``, ``0``, ``-1``, ``-2``) as strings.
    crew_config:
        Config dict passed to :func:`aqp.agents.trading.propagate.propagate`
        in live / audit modes.
    """

    def __init__(
        self,
        strategy_id: str = "default",
        cache_root: str | None = None,
        mode: str | AgenticAlphaMode = AgenticAlphaMode.PRECOMPUTE,
        audit_fraction: float | None = None,
        min_confidence: float = 0.0,
        rating_size_map: dict[str, float] | None = None,
        crew_config: dict[str, Any] | None = None,
        tools: list[str] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        memory: dict[str, Any] | None = None,
        guardrails: dict[str, Any] | None = None,
        output_schema: Any = None,
        max_cost_usd: float = 1.0,
        max_calls: int = 20,
    ) -> None:
        self.strategy_id = strategy_id
        self.cache = DecisionCache(root=cache_root, strategy_id=strategy_id)
        self.mode = AgenticAlphaMode(str(mode))
        try:
            default_audit = float(getattr(settings, "agentic_audit_fraction", 0.0) or 0.0)
        except Exception:
            default_audit = 0.0
        self.audit_fraction = (
            float(audit_fraction) if audit_fraction is not None else default_audit
        )
        self.min_confidence = float(min_confidence)
        self.rating_size_map = {
            str(k): float(v) for k, v in (rating_size_map or {}).items()
        }
        # First-class capability layer — tools / MCP / memory / guardrails /
        # structured output / cost + rate limits. Stored on the alpha so
        # the wizard can render them later, plus passed through
        # ``crew_config["capabilities"]`` so live / audit modes propagate
        # the same shape into ``run_trader_crew``.
        self.capabilities_dict: dict[str, Any] = {
            "tools": list(tools or []),
            "mcp_servers": list(mcp_servers or []),
            "memory": memory,
            "guardrails": guardrails,
            "output_schema": output_schema,
            "max_cost_usd": float(max_cost_usd),
            "max_calls": int(max_calls),
        }
        self.crew_config = dict(crew_config or {})
        if self.capabilities_dict["tools"] or self.capabilities_dict["mcp_servers"] or memory or guardrails or output_schema:
            self.crew_config.setdefault("capabilities", self.capabilities_dict)
        self._rng = random.Random(42)
        # Telemetry — surfaced by the task runner so the UI can report
        # cache hit-rate and live fallback counts.
        self.stats: dict[str, int] = {
            "bars": 0,
            "hits": 0,
            "misses": 0,
            "live_calls": 0,
            "audit_calls": 0,
            "hold_skips": 0,
            "low_confidence_skips": 0,
        }

    # ------------------------------------------------------------------
    # IAlphaModel API
    # ------------------------------------------------------------------

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        ts = context.get("current_time") or context.get("timestamp")
        if ts is None:
            # Happens in mock tests — fall back to the last timestamp in bars.
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
            signal = self._to_signal(sym, decision, ts)
            if signal is not None:
                signals.append(signal)
        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decision_for(self, vt_symbol: str, ts: Any) -> AgentDecision | None:
        cached = self.cache.get(vt_symbol, ts)

        if self.mode == AgenticAlphaMode.PRECOMPUTE:
            if cached is not None:
                self.stats["hits"] += 1
            return cached

        if self.mode == AgenticAlphaMode.LIVE:
            self.stats["live_calls"] += 1
            return self._run_live(vt_symbol, ts)

        # precompute_plus_audit
        if cached is None:
            self.stats["live_calls"] += 1
            return self._run_live(vt_symbol, ts)

        self.stats["hits"] += 1
        if self._rng.random() < self.audit_fraction:
            self.stats["audit_calls"] += 1
            live = self._run_live(vt_symbol, ts, force=True)
            if live is not None and live.action != cached.action:
                logger.info(
                    "audit delta %s @ %s: cached=%s live=%s",
                    vt_symbol,
                    ts,
                    cached.action.value,
                    live.action.value,
                )
        return cached

    def _run_live(
        self,
        vt_symbol: str,
        ts: Any,
        *,
        force: bool = False,
    ) -> AgentDecision | None:
        try:
            from aqp.agents.trading.propagate import propagate

            return propagate(
                vt_symbol,
                ts,
                config=self.crew_config or None,
                cache=self.cache,
                force=force,
            )
        except Exception as exc:
            logger.warning("live crew call failed for %s @ %s: %s", vt_symbol, ts, exc)
            return None

    def _to_signal(
        self,
        sym: Symbol,
        decision: AgentDecision,
        ts: Any,
    ) -> Signal | None:
        if decision.action == TraderAction.HOLD:
            self.stats["hold_skips"] += 1
            return None
        if decision.confidence < self.min_confidence:
            self.stats["low_confidence_skips"] += 1
            return None

        size = float(decision.size_pct)
        if self.rating_size_map:
            rating_key = decision.rating.value
            numeric_key = str(
                {"strong_buy": 2, "buy": 1, "hold": 0, "sell": -1, "strong_sell": -2}
                .get(rating_key, 0)
            )
            size = float(
                self.rating_size_map.get(rating_key)
                or self.rating_size_map.get(numeric_key)
                or size
            )
        size = max(0.0, min(1.0, size))
        if size <= 0.0:
            self.stats["hold_skips"] += 1
            return None

        direction = _ACTION_TO_DIRECTION.get(decision.action)
        if direction is None:
            return None

        return Signal(
            symbol=sym,
            strength=size,
            direction=direction,
            timestamp=ts,
            confidence=float(decision.confidence),
            horizon_days=int(decision.trader_plan.horizon_days) if decision.trader_plan else 5,
            source=f"AgenticAlpha({self.strategy_id})",
            rationale=decision.rationale or None,
        )

    # ------------------------------------------------------------------
    # Debug / introspection
    # ------------------------------------------------------------------

    @property
    def cache_root(self) -> Path:
        return self.cache.root

    def hit_rate(self) -> float:
        hits = self.stats["hits"]
        misses = self.stats["misses"]
        denom = hits + misses
        return hits / denom if denom else 0.0
