"""Historical volatility tool — exposes annualised return-vol per symbol.

This is the first of three Phase-4 tools that surface deterministic
quantitative primitives to spec-driven agents. Following the report's
guidance, the agent never re-derives volatility from raw bars itself —
it always invokes this tool, which uses the same Iceberg-backed
``DuckDBHistoryProvider`` as the rest of the platform.

The tool returns a JSON-serialisable mapping that includes the raw
sigma, the bar count actually used (so the agent can audit window
adequacy), and the lookback window in days. Agents should refuse to act
on a sigma derived from < 20 bars.
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


class HistoricalVolatilityInput(BaseModel):
    vt_symbol: str = Field(
        ...,
        description="Canonical AQP symbol id, e.g. 'SPY.NASDAQ'. Never split on '.'.",
    )
    period_days: int = Field(
        default=63,
        ge=2,
        le=2520,
        description="Lookback window in trading days (default ~3 months).",
    )
    annualise: bool = Field(
        default=True,
        description=(
            "Multiply the per-bar sigma by sqrt(252) to express in annual "
            "terms. Disable when comparing against another tool that returns "
            "per-bar volatility."
        ),
    )


class HistoricalVolatilityTool(BaseTool):
    """MCP tool: ``get_historical_volatility(vt_symbol, period_days)``."""

    name: str = "historical_volatility"
    description: str = (
        "Compute the historical close-to-close volatility for a symbol over the "
        "requested lookback window. Returns the (annualised by default) sigma, "
        "the bar count used, the start/end timestamps, and a flag indicating "
        "whether the sample size meets the 20-bar minimum recommended by the "
        "Risk Simulator agent."
    )
    args_schema: type[BaseModel] = HistoricalVolatilityInput

    def _run(  # type: ignore[override]
        self,
        vt_symbol: str,
        period_days: int = 63,
        annualise: bool = True,
    ) -> str:
        from datetime import datetime, timedelta

        try:
            from aqp.core.types import Symbol
            from aqp.data.duckdb_engine import DuckDBHistoryProvider

            symbol = Symbol.parse(vt_symbol)
            end = datetime.utcnow()
            # Pad the request so weekends + holidays don't starve a 20-bar
            # minimum. 1.6x is conservative for daily bars on US equities.
            start = end - timedelta(days=int(period_days * 1.6) + 7)
            bars = DuckDBHistoryProvider().get_bars(
                symbols=[symbol], start=start, end=end
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("historical_volatility(%s) failed", vt_symbol)
            return json.dumps({"error": str(exc), "vt_symbol": vt_symbol})

        if bars is None or len(bars) == 0:
            return json.dumps(
                {
                    "vt_symbol": vt_symbol,
                    "sigma": None,
                    "bars_used": 0,
                    "error": "no bars in window",
                }
            )

        try:
            import polars as pl

            plf = (
                pl.from_pandas(bars)
                .lazy()
                .filter(pl.col("vt_symbol") == vt_symbol)
                .sort("timestamp")
                .tail(period_days + 1)
                .with_columns(
                    pl.col("close").cast(pl.Float64),
                )
                .with_columns(
                    (
                        pl.col("close").pct_change()
                    ).alias("ret"),
                )
                .drop_nulls(subset=["ret"])
                .collect(streaming=True)
            )
            n = plf.height
            if n < 2:
                return json.dumps(
                    {
                        "vt_symbol": vt_symbol,
                        "sigma": None,
                        "bars_used": n,
                        "error": "fewer than 2 returns",
                    }
                )
            sigma = float(plf.get_column("ret").std(ddof=1) or 0.0)
            mu = float(plf.get_column("ret").mean() or 0.0)
            ts_min = str(plf.get_column("timestamp").min())
            ts_max = str(plf.get_column("timestamp").max())
        except Exception as exc:  # noqa: BLE001
            logger.exception("polars vol calc failed for %s", vt_symbol)
            return json.dumps({"error": str(exc), "vt_symbol": vt_symbol})

        if annualise:
            sigma *= math.sqrt(_TRADING_DAYS_PER_YEAR)
            mu_label = "mu_annualised"
            mu *= _TRADING_DAYS_PER_YEAR
        else:
            mu_label = "mu_per_bar"

        result: dict[str, Any] = {
            "vt_symbol": vt_symbol,
            "sigma": sigma,
            mu_label: mu,
            "bars_used": n,
            "period_days_requested": int(period_days),
            "annualised": bool(annualise),
            "window_start": ts_min,
            "window_end": ts_max,
            "meets_min_sample": bool(n >= 20),
        }
        return json.dumps(result, default=str)


__all__ = ["HistoricalVolatilityInput", "HistoricalVolatilityTool"]
