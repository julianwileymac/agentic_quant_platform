"""CrewAI tool: pull windowed performance indicators for the trader agent."""
from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class PerformanceWindowInput(BaseModel):
    vt_symbol: str
    lookback_days: int = Field(default=60, ge=5, le=500)
    indicators: list[str] = Field(
        default_factory=lambda: ["sma_20", "rsi_14", "atr_14", "vol_pct", "return_5d", "return_20d"],
    )


class PerformanceWindowTool(BaseTool):
    name: str = "performance_window"
    description: str = (
        "Return a compact JSON summary of the most recent windowed indicators "
        "for a symbol (volatility, returns, RSI, ATR, ...)."
    )
    args_schema: type[BaseModel] = PerformanceWindowInput

    def _run(  # type: ignore[override]
        self,
        vt_symbol: str,
        lookback_days: int = 60,
        indicators: list[str] | None = None,
    ) -> str:
        try:
            import pandas as pd

            from aqp.data.bars import get_bars
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: bars/pandas unavailable: {exc}"
        try:
            df = get_bars(vt_symbol, lookback_days=lookback_days)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: failed to fetch bars for {vt_symbol}: {exc}"
        if df is None or df.empty:
            return f"No bars for {vt_symbol}"
        df = df.tail(lookback_days)
        closes = df["close"].astype(float)
        rets = closes.pct_change().dropna()
        last = float(closes.iloc[-1])
        out: dict[str, Any] = {
            "vt_symbol": vt_symbol,
            "as_of": str(df.index[-1]) if df.index.name else str(df.iloc[-1].get("timestamp", "")),
            "last_close": round(last, 4),
            "return_1d": round(float(rets.iloc[-1]) * 100, 4) if len(rets) else 0.0,
            "return_5d": round(float(rets.tail(5).sum()) * 100, 4) if len(rets) >= 5 else 0.0,
            "return_20d": round(float(rets.tail(20).sum()) * 100, 4) if len(rets) >= 20 else 0.0,
            "vol_pct": round(float(rets.std()) * (252**0.5) * 100, 4),
        }
        if "sma_20" in (indicators or []) and len(closes) >= 20:
            out["sma_20"] = round(float(closes.tail(20).mean()), 4)
            out["above_sma_20"] = bool(last > out["sma_20"])
        if "atr_14" in (indicators or []) and {"high", "low"}.issubset(df.columns):
            tr = (df["high"].astype(float) - df["low"].astype(float)).abs()
            out["atr_14"] = round(float(tr.tail(14).mean()), 4)
        if "rsi_14" in (indicators or []) and len(rets) >= 14:
            up = rets.clip(lower=0).tail(14).mean()
            dn = -rets.clip(upper=0).tail(14).mean() or 1e-9
            rs = up / dn
            out["rsi_14"] = round(100 - 100 / (1 + rs), 2)
        import json

        return json.dumps(out, default=str, indent=2)


__all__ = ["PerformanceWindowTool"]
