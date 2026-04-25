"""FinRobot Market Forecaster — narrative + numeric forecast at multiple horizons."""
from __future__ import annotations

import json
from typing import Any

from aqp.agents.financial.base import BaseFinancialCrew, FinancialReport
from aqp.core.registry import agent


_SYSTEM = """\
You are a FinRobot Market Forecaster. Given recent prices, fundamentals
and a news digest, produce next-week, next-month, and next-quarter
point forecasts with directional probability and rationale.

Respond ONLY with JSON with keys:
  horizons: [{
    horizon: "1W" | "1M" | "3M",
    pct_change: number,
    direction: "UP" | "DOWN" | "FLAT",
    probability_up: number (0..1),
    rationale: string,
    key_risks: [string]
  }]
"""


@agent("MarketForecasterCrew", tags=("llm-crew", "forecast", "finrobot"))
class MarketForecaster(BaseFinancialCrew):
    name = "market-forecaster"

    def run(
        self,
        *,
        ticker: str,
        as_of: str,
        price_summary: dict[str, Any],
        fundamentals: dict[str, Any] | None = None,
        news_digest: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> FinancialReport:
        user = (
            f"ticker: {ticker}\n"
            f"as_of: {as_of}\n"
            f"price_summary: {json.dumps(price_summary, default=str)}\n"
            f"fundamentals: {json.dumps(fundamentals or {}, default=str)[:3000]}\n"
            f"news_digest: {json.dumps(news_digest or [], default=str)[:3000]}\n"
        )
        call = self._call(_SYSTEM, user, tier=self.tier)
        horizons = list(call["payload"].get("horizons", []) or [])
        return FinancialReport(
            title=f"Market Forecast: {ticker}",
            as_of=as_of,
            payload={"ticker": ticker, "horizons": horizons},
            sections=[{"name": h.get("horizon", "?"), "body": h} for h in horizons],
            usage=self._usage([call]),
        )


__all__ = ["MarketForecaster"]
