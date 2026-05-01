"""Insight-impact simulator — Monte Carlo stress test for a proposed signal.

This is the headline Phase-4 tool: the Risk Simulator agent invokes it
to evaluate a draft :class:`Signal` (or ``insight`` in Lean parlance)
*before* the consensus gate releases a ``SignalEvent`` to the Phase-1
event-driven engine. The tool returns a structured verdict the gate can
match against deterministic thresholds.

Mechanics
---------

1. Pull ``lookback_days`` of close-to-close returns for the insight's
   symbol from the Iceberg-backed ``DuckDBHistoryProvider``.
2. Construct ``n_simulations`` bootstrap return paths over
   ``horizon_days`` using non-parametric resampling (preserves fat tails
   without assuming Gaussianity).
3. Apply the proposed insight's directional bet (LONG → +1, SHORT → -1)
   weighted by ``strength`` and ``confidence``.
4. Compute the path-level statistics the Risk Simulator agent uses to
   decide approval:

   * ``expected_return``
   * ``expected_sharpe``
   * ``p99_drawdown``  (worst max-drawdown across simulations)
   * ``tvar_95``        (closed-form Gaussian TVaR for direct comparison
     to the :class:`TVaRInterceptor` risk model)
   * ``approved``        (auto-pass when all of the above clear the
     hard-coded thresholds — overridable via ``thresholds=`` kwarg)

The tool is deliberately read-only: it never writes ``Signal`` rows or
``SignalEvent``s itself. The agent is responsible for calling
``emit_signal_event`` only when ``approved`` is true.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


_TRADING_DAYS_PER_YEAR = 252
_DEFAULT_THRESHOLDS = {
    "max_p99_drawdown": 0.20,
    "max_tvar_95": 0.10,
    "min_expected_sharpe": 0.0,
}


class InsightInput(BaseModel):
    vt_symbol: str = Field(..., description="Insight symbol id, e.g. 'AAPL.NASDAQ'.")
    direction: str = Field(
        ...,
        description=(
            "'long' or 'short'. Mapped to +1/-1 multipliers on the bootstrapped "
            "return paths."
        ),
    )
    strength: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Insight strength in [0, 1].",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Insight confidence in [0, 1].",
    )


class SimulateInsightInput(BaseModel):
    insight: InsightInput
    horizon_days: int = Field(default=10, ge=1, le=252)
    lookback_days: int = Field(default=252, ge=20, le=2520)
    n_simulations: int = Field(default=1000, ge=50, le=20000)
    seed: int | None = Field(
        default=None,
        description="Optional RNG seed for deterministic agent re-runs.",
    )
    thresholds: dict[str, float] | None = Field(
        default=None,
        description=(
            "Override the default approval thresholds. Keys: "
            "max_p99_drawdown, max_tvar_95, min_expected_sharpe."
        ),
    )


class InsightImpactTool(BaseTool):
    """MCP tool: ``simulate_insight_impact(insight, horizon_days, n_simulations)``."""

    name: str = "insight_impact"
    description: str = (
        "Run a non-parametric Monte Carlo stress test on a draft insight. "
        "Returns expected return, Sharpe, p99 max-drawdown, Gaussian TVaR(0.95), "
        "and an ``approved`` flag computed against per-call thresholds. The "
        "Risk Simulator agent treats ``approved=false`` as a veto on the "
        "consensus gate — no SignalEvent is emitted."
    )
    args_schema: type[BaseModel] = SimulateInsightInput

    def _run(  # type: ignore[override]
        self,
        insight: InsightInput | dict[str, Any],
        horizon_days: int = 10,
        lookback_days: int = 252,
        n_simulations: int = 1000,
        seed: int | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> str:
        if isinstance(insight, dict):
            try:
                insight = InsightInput.model_validate(insight)
            except Exception as exc:  # noqa: BLE001
                return json.dumps({"error": f"invalid insight: {exc}"})

        try:
            import numpy as np
        except ImportError:  # pragma: no cover
            return json.dumps({"error": "numpy not available"})

        try:
            from datetime import datetime, timedelta

            from aqp.core.types import Symbol
            from aqp.data.duckdb_engine import DuckDBHistoryProvider

            symbol = Symbol.parse(insight.vt_symbol)
            end = datetime.utcnow()
            start = end - timedelta(days=int(lookback_days * 1.6) + 7)
            bars = DuckDBHistoryProvider().get_bars(
                symbols=[symbol], start=start, end=end
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("insight_impact: bar fetch failed")
            return json.dumps({"error": f"bar fetch: {exc}"})

        if bars is None or len(bars) == 0:
            return json.dumps(
                {
                    "approved": False,
                    "error": "no historical bars",
                    "vt_symbol": insight.vt_symbol,
                }
            )

        try:
            import polars as pl

            returns = (
                pl.from_pandas(bars)
                .lazy()
                .filter(pl.col("vt_symbol") == insight.vt_symbol)
                .sort("timestamp")
                .with_columns(pl.col("close").cast(pl.Float64).pct_change().alias("ret"))
                .drop_nulls(subset=["ret"])
                .select("ret")
                .collect(streaming=True)
                .get_column("ret")
                .to_numpy()
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"return panel: {exc}"})

        if returns.size < 20:
            return json.dumps(
                {
                    "approved": False,
                    "error": f"insufficient history: {returns.size} returns",
                    "vt_symbol": insight.vt_symbol,
                }
            )

        rng = np.random.default_rng(seed)
        # Bootstrap n_simulations paths of horizon_days resampled returns.
        idx = rng.integers(0, returns.size, size=(n_simulations, horizon_days))
        sampled = returns[idx]
        direction_mult = 1.0 if insight.direction.lower() == "long" else -1.0
        weight = insight.strength * insight.confidence
        path_returns = direction_mult * weight * sampled  # (n_sims, horizon)
        cumulative = np.cumprod(1.0 + path_returns, axis=1)
        terminal_returns = cumulative[:, -1] - 1.0

        # Per-path running max for max-drawdown.
        running_max = np.maximum.accumulate(cumulative, axis=1)
        drawdowns = (cumulative - running_max) / running_max
        max_dd_per_path = drawdowns.min(axis=1)
        p99_drawdown = float(-np.quantile(max_dd_per_path, 0.01))

        expected_return = float(terminal_returns.mean())
        return_std = float(terminal_returns.std(ddof=1)) if terminal_returns.size > 1 else 0.0
        # Annualise the per-horizon Sharpe to make it comparable to standard
        # quant tooling (assumes returns are roughly i.i.d. over the horizon).
        if return_std > 0:
            scale = math.sqrt(_TRADING_DAYS_PER_YEAR / max(horizon_days, 1))
            expected_sharpe = (expected_return / return_std) * scale
        else:
            expected_sharpe = 0.0

        # Gaussian TVaR(0.95) on the terminal return distribution — same
        # closed-form as TVaRInterceptor.tvar_normal so the two metrics are
        # directly comparable.
        try:
            from aqp.strategies.risk_models import TVaRInterceptor

            tvar_95 = abs(
                TVaRInterceptor.tvar_normal(expected_return, return_std, 0.95)
            )
        except Exception:
            tvar_95 = 0.0

        thr = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
        approved = (
            p99_drawdown <= thr["max_p99_drawdown"]
            and tvar_95 <= thr["max_tvar_95"]
            and expected_sharpe >= thr["min_expected_sharpe"]
        )

        return json.dumps(
            {
                "approved": bool(approved),
                "vt_symbol": insight.vt_symbol,
                "direction": insight.direction.lower(),
                "horizon_days": int(horizon_days),
                "lookback_days": int(lookback_days),
                "n_simulations": int(n_simulations),
                "expected_return": expected_return,
                "expected_sharpe": expected_sharpe,
                "p99_drawdown": p99_drawdown,
                "tvar_95": tvar_95,
                "thresholds": thr,
                "rationale": (
                    f"approved={approved}; tvar_95={tvar_95:.4f} (max {thr['max_tvar_95']}), "
                    f"p99_dd={p99_drawdown:.4f} (max {thr['max_p99_drawdown']}), "
                    f"sharpe={expected_sharpe:.3f} (min {thr['min_expected_sharpe']})"
                ),
            },
            default=str,
        )


__all__ = ["InsightImpactTool", "InsightInput", "SimulateInsightInput"]
