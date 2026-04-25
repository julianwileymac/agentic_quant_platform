"""Metrics that measure the *quality* of an LLM trader's decisions.

The existing :mod:`aqp.backtest.metrics` module captures portfolio-level
performance (Sharpe, Sortino, drawdown). These metrics answer
different questions:

- Did the agent's ratings align with the forward return?
- How much did each decision cost on average?
- Does investing more in the debate (more rounds, more analysts) pay
  off in realized Sharpe?

Inputs are either a list/DataFrame of :class:`AgentDecision`-shaped
rows (as persisted to the ``agent_decisions`` table) or a
:class:`DecisionCache` scan result, plus the bar table used by the
backtest engine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


_RATING_SIGN = {
    "strong_buy": 1.0,
    "buy": 1.0,
    "hold": 0.0,
    "sell": -1.0,
    "strong_sell": -1.0,
}


def _as_decisions_df(source: Any) -> pd.DataFrame:
    """Normalize any supported input into a tidy DataFrame."""
    if isinstance(source, pd.DataFrame):
        return source
    if isinstance(source, list):
        if not source:
            return pd.DataFrame()
        if hasattr(source[0], "model_dump"):
            return pd.DataFrame([d.model_dump(mode="json") for d in source])
        return pd.DataFrame(source)
    raise TypeError(f"unsupported source type: {type(source).__name__}")


def forward_return(bars: pd.DataFrame, vt_symbol: str, ts: Any, horizon_days: int) -> float:
    """Return the close-to-close forward return over ``horizon_days``."""
    sub = bars[bars["vt_symbol"] == vt_symbol].sort_values("timestamp")
    if sub.empty:
        return float("nan")
    sub = sub.reset_index(drop=True)
    try:
        idx = sub[sub["timestamp"] >= pd.Timestamp(ts)].index[0]
    except IndexError:
        return float("nan")
    try:
        start = float(sub.iloc[idx]["close"])
        end = float(sub.iloc[min(idx + horizon_days, len(sub) - 1)]["close"])
    except Exception:
        return float("nan")
    if start == 0:
        return float("nan")
    return (end - start) / start


@dataclass
class AgenticMetrics:
    n_decisions: int
    hit_rate: float
    rating_hit_rate: float
    mean_cost_usd: float
    total_cost_usd: float
    cost_per_buy: float
    mean_confidence: float
    confidence_hit_corr: float
    n_debate_turns: int = 0
    mean_debate_turns_per_decision: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "n_decisions": float(self.n_decisions),
            "hit_rate": self.hit_rate,
            "rating_hit_rate": self.rating_hit_rate,
            "mean_cost_usd": self.mean_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "cost_per_buy": self.cost_per_buy,
            "mean_confidence": self.mean_confidence,
            "confidence_hit_corr": self.confidence_hit_corr,
            "n_debate_turns": float(self.n_debate_turns),
            "mean_debate_turns_per_decision": self.mean_debate_turns_per_decision,
        }


def evaluate(
    decisions: Any,
    bars: pd.DataFrame,
    *,
    horizon_days: int = 5,
    debate_turns: int | None = None,
) -> AgenticMetrics:
    """Compute a full :class:`AgenticMetrics` over the supplied decisions."""
    df = _as_decisions_df(decisions)
    if df.empty:
        return AgenticMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    ts_col = "ts" if "ts" in df.columns else "timestamp"
    df = df.copy()
    df[ts_col] = pd.to_datetime(df[ts_col])
    df["action"] = df.get("action", "HOLD").astype(str).str.upper()
    df["rating"] = df.get("rating", "hold").astype(str).str.lower()
    df["confidence"] = pd.to_numeric(df.get("confidence", 0.5), errors="coerce").fillna(0.5)
    df["token_cost_usd"] = pd.to_numeric(df.get("token_cost_usd", 0.0), errors="coerce").fillna(0.0)

    df["forward_return"] = [
        forward_return(bars, row["vt_symbol"], row[ts_col], horizon_days)
        for _, row in df.iterrows()
    ]

    # Hit-rate (action aligned with forward return).
    action_sign = df["action"].map({"BUY": 1, "SELL": -1, "HOLD": 0}).fillna(0)
    rating_sign = df["rating"].map(_RATING_SIGN).fillna(0)
    ret_sign = np.sign(df["forward_return"])
    action_hits = (action_sign * ret_sign > 0).astype(int)
    rating_hits = (rating_sign * ret_sign > 0).astype(int)

    n_buys = int((df["action"] == "BUY").sum())
    total_cost = float(df["token_cost_usd"].sum())
    cost_per_buy = (total_cost / n_buys) if n_buys else 0.0

    try:
        conf_hit_corr = float(df["confidence"].corr(action_hits))
    except Exception:
        conf_hit_corr = 0.0
    if np.isnan(conf_hit_corr):
        conf_hit_corr = 0.0

    return AgenticMetrics(
        n_decisions=int(len(df)),
        hit_rate=float(action_hits.mean()) if len(df) else 0.0,
        rating_hit_rate=float(rating_hits.mean()) if len(df) else 0.0,
        mean_cost_usd=float(df["token_cost_usd"].mean()) if len(df) else 0.0,
        total_cost_usd=total_cost,
        cost_per_buy=cost_per_buy,
        mean_confidence=float(df["confidence"].mean()) if len(df) else 0.0,
        confidence_hit_corr=conf_hit_corr,
        n_debate_turns=int(debate_turns or 0),
        mean_debate_turns_per_decision=(
            float(debate_turns) / len(df) if debate_turns and len(df) else 0.0
        ),
    )
