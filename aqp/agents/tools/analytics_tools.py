"""9 new agent tools added by the inspiration rehydration.

All inherit from ``crewai.tools.BaseTool`` (or the import-time shim in
``aqp.agents.tools.__init__``) and return JSON strings.

Tools:
- ``cointegration_tool`` — runs ADF + Engle-Granger on a pair.
- ``regime_classifier_tool`` — ADX trend/range classifier.
- ``realised_vol_tool`` — five OHLC vol estimators.
- ``factor_screen_tool`` — Polars factor expression DSL.
- ``hft_metrics_tool`` — HFT-aware metrics on a backtest result.
- ``multi_indicator_vote_tool`` — TradFiInspired-style consensus.
- ``chart_pattern_tool`` — extrema + chart pattern detection.
- ``option_greeks_tool`` — Bachelier + inverse Greeks.
- ``option_spread_tool`` — vertical spread P&L math.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cointegration
# ---------------------------------------------------------------------------


class CointegrationInput(BaseModel):
    vt_symbol_a: str = Field(..., description="First leg vt_symbol")
    vt_symbol_b: str = Field(..., description="Second leg vt_symbol")
    period_days: int = Field(default=252, ge=30, le=2520)
    z_window: int = Field(default=60, ge=10, le=252)


class CointegrationTool(BaseTool):
    name: str = "cointegration_tool"
    description: str = (
        "Run ADF + Engle-Granger cointegration tests on a pair of symbols. "
        "Returns p-value, hedge ratio, current spread z-score, and OU half-life."
    )
    args_schema: type[BaseModel] = CointegrationInput

    def _run(self, vt_symbol_a: str, vt_symbol_b: str, period_days: int = 252, z_window: int = 60) -> str:
        try:
            from datetime import datetime, timedelta
            from aqp.core.types import Symbol
            from aqp.data.cointegration import engle_granger
            from aqp.data.duckdb_engine import DuckDBHistoryProvider
            sym_a = Symbol.parse(vt_symbol_a)
            sym_b = Symbol.parse(vt_symbol_b)
            end = datetime.utcnow()
            start = end - timedelta(days=int(period_days * 1.6) + 30)
            bars = DuckDBHistoryProvider().get_bars(symbols=[sym_a, sym_b], start=start, end=end)
            if bars is None or bars.empty:
                return json.dumps({"error": "no bars in window", "vt_symbol_a": vt_symbol_a, "vt_symbol_b": vt_symbol_b})
            a = bars[bars["vt_symbol"] == vt_symbol_a].sort_values("timestamp").set_index("timestamp")["close"]
            b = bars[bars["vt_symbol"] == vt_symbol_b].sort_values("timestamp").set_index("timestamp")["close"]
            res = engle_granger(a, b, z_window=z_window)
            return json.dumps({
                "vt_symbol_a": vt_symbol_a, "vt_symbol_b": vt_symbol_b,
                "cointegrated": res.cointegrated, "p_value": res.p_value,
                "hedge_ratio": res.hedge_ratio, "intercept": res.intercept,
                "spread_z_latest": float(res.spread_z.iloc[-1]) if len(res.spread_z) else None,
                "half_life_bars": res.half_life,
            }, default=str)
        except Exception as exc:  # noqa: BLE001
            logger.exception("cointegration_tool failed")
            return json.dumps({"error": str(exc), "vt_symbol_a": vt_symbol_a, "vt_symbol_b": vt_symbol_b})


# ---------------------------------------------------------------------------
# Regime classifier (ADX trend/range)
# ---------------------------------------------------------------------------


class RegimeClassifierInput(BaseModel):
    vt_symbol: str = Field(...)
    period_days: int = Field(default=63, ge=14, le=2520)
    adx_threshold: float = Field(default=25.0, ge=10.0, le=60.0)


class RegimeClassifierTool(BaseTool):
    name: str = "regime_classifier_tool"
    description: str = (
        "Classify the current regime as trending vs ranging using ADX threshold. "
        "Returns the latest ADX, the regime label, and a score (ADX - threshold)."
    )
    args_schema: type[BaseModel] = RegimeClassifierInput

    def _run(self, vt_symbol: str, period_days: int = 63, adx_threshold: float = 25.0) -> str:
        try:
            from datetime import datetime, timedelta
            from aqp.core.types import Symbol
            from aqp.data.duckdb_engine import DuckDBHistoryProvider
            from aqp.data.regime import ADXRegimeClassifier
            from aqp.strategies.qtradex.alphas import _adx
            sym = Symbol.parse(vt_symbol)
            end = datetime.utcnow()
            start = end - timedelta(days=int(period_days * 1.6) + 14)
            bars = DuckDBHistoryProvider().get_bars(symbols=[sym], start=start, end=end)
            if bars is None or bars.empty:
                return json.dumps({"error": "no bars", "vt_symbol": vt_symbol})
            sub = bars[bars["vt_symbol"] == vt_symbol].sort_values("timestamp")
            adx_series = _adx(sub["high"], sub["low"], sub["close"])
            adx_value = float(adx_series.iloc[-1]) if not adx_series.empty else float("nan")
            classifier = ADXRegimeClassifier(threshold=adx_threshold)
            reading = classifier.latest(adx_value)
            return json.dumps({
                "vt_symbol": vt_symbol, "adx": adx_value, "threshold": adx_threshold,
                "regime": reading.regime.value, "score": reading.score,
            }, default=str)
        except Exception as exc:  # noqa: BLE001
            logger.exception("regime_classifier_tool failed")
            return json.dumps({"error": str(exc), "vt_symbol": vt_symbol})


# ---------------------------------------------------------------------------
# Realised volatility (5 estimators)
# ---------------------------------------------------------------------------


class RealisedVolInput(BaseModel):
    vt_symbol: str = Field(...)
    period_days: int = Field(default=63, ge=10, le=2520)
    estimator_period: int = Field(default=20, ge=5, le=252)


class RealisedVolTool(BaseTool):
    name: str = "realised_vol_tool"
    description: str = (
        "Compute five OHLC realised-vol estimators (close-to-close, Parkinson, "
        "Garman-Klass, Rogers-Satchell, Yang-Zhang) and return the latest annualised "
        "values in a single JSON object."
    )
    args_schema: type[BaseModel] = RealisedVolInput

    def _run(self, vt_symbol: str, period_days: int = 63, estimator_period: int = 20) -> str:
        try:
            from datetime import datetime, timedelta
            from aqp.core.types import Symbol
            from aqp.data.duckdb_engine import DuckDBHistoryProvider
            from aqp.data.realised_volatility import compare_estimators
            sym = Symbol.parse(vt_symbol)
            end = datetime.utcnow()
            start = end - timedelta(days=int(period_days * 1.6) + estimator_period)
            bars = DuckDBHistoryProvider().get_bars(symbols=[sym], start=start, end=end)
            if bars is None or bars.empty:
                return json.dumps({"error": "no bars", "vt_symbol": vt_symbol})
            sub = bars[bars["vt_symbol"] == vt_symbol].sort_values("timestamp").reset_index(drop=True)
            df = compare_estimators(sub, period=estimator_period)
            latest = df.iloc[-1].to_dict()
            return json.dumps({
                "vt_symbol": vt_symbol, "period": estimator_period,
                "estimators": {k: (None if v != v else float(v)) for k, v in latest.items()},
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("realised_vol_tool failed")
            return json.dumps({"error": str(exc), "vt_symbol": vt_symbol})


# ---------------------------------------------------------------------------
# Factor screen
# ---------------------------------------------------------------------------


class FactorScreenInput(BaseModel):
    vt_symbols: list[str] = Field(..., description="Universe to screen")
    expression: str = Field(..., description="Factor expression e.g. 'Rank(Ts_Mean(close, 20))'")
    period_days: int = Field(default=120, ge=30, le=2520)
    top_k: int = Field(default=10, ge=1, le=200)


class FactorScreenTool(BaseTool):
    name: str = "factor_screen_tool"
    description: str = (
        "Evaluate a factor expression (Alpha101 DSL) across a universe and return "
        "the top-K symbols by latest factor value."
    )
    args_schema: type[BaseModel] = FactorScreenInput

    def _run(self, vt_symbols: list[str], expression: str, period_days: int = 120, top_k: int = 10) -> str:
        try:
            from datetime import datetime, timedelta
            from aqp.core.types import Symbol
            from aqp.data.duckdb_engine import DuckDBHistoryProvider
            from aqp.data.factor_expression import FactorEngine, panel_from_bars
            symbols = [Symbol.parse(s) for s in vt_symbols]
            end = datetime.utcnow()
            start = end - timedelta(days=int(period_days * 1.6))
            bars = DuckDBHistoryProvider().get_bars(symbols=symbols, start=start, end=end)
            if bars is None or bars.empty:
                return json.dumps({"error": "no bars"})
            panel = panel_from_bars(bars)
            engine = FactorEngine(panel)
            factor = engine.evaluate(expression)
            latest = factor.groupby(level="vt_symbol").last().sort_values(ascending=False).head(top_k)
            return json.dumps({
                "expression": expression,
                "top_k": int(top_k),
                "rankings": [{"vt_symbol": k, "value": float(v) if v == v else None} for k, v in latest.items()],
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("factor_screen_tool failed")
            return json.dumps({"error": str(exc), "expression": expression})


# ---------------------------------------------------------------------------
# HFT metrics
# ---------------------------------------------------------------------------


class HftMetricsInput(BaseModel):
    backtest_run_id: str = Field(..., description="ID of the backtest run to analyse")
    days_per_year: int = Field(default=365, ge=252, le=365)


class HftMetricsTool(BaseTool):
    name: str = "hft_metrics_tool"
    description: str = (
        "Compute HFT-aware metrics (sample-aware Sharpe/Sortino, max position, "
        "leverage, return-over-trade, fill ratio) for a completed backtest run."
    )
    args_schema: type[BaseModel] = HftMetricsInput

    def _run(self, backtest_run_id: str, days_per_year: int = 365) -> str:
        try:
            import pandas as pd
            from aqp.backtest.hft_metrics import hft_summary
            # In production this would load the backtest result from Postgres.
            # For now we return a stub indicating where the data should come from.
            stub_returns = pd.Series([], dtype=float)
            stub_positions = pd.Series([], dtype=float)
            stub_equity = pd.Series([], dtype=float)
            summary = hft_summary(stub_returns, stub_positions, stub_equity, days_per_year=days_per_year)
            return json.dumps({
                "backtest_run_id": backtest_run_id,
                "summary": summary,
                "note": "Stub — wire the BacktestRun loader before production use.",
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("hft_metrics_tool failed")
            return json.dumps({"error": str(exc), "backtest_run_id": backtest_run_id})


# ---------------------------------------------------------------------------
# Multi-indicator vote
# ---------------------------------------------------------------------------


class MultiIndicatorVoteInput(BaseModel):
    vt_symbol: str = Field(...)
    period_days: int = Field(default=120, ge=30, le=2520)
    indicators: list[str] = Field(default_factory=lambda: ["SMA:20", "SMA:50", "EMA:12", "EMA:26", "RSI:14", "MACD"])


class MultiIndicatorVoteTool(BaseTool):
    name: str = "multi_indicator_vote_tool"
    description: str = (
        "Compute a TradFi-style consensus vote across N classical indicators. "
        "Returns the bullish vote count, bearish vote count, and per-indicator status."
    )
    args_schema: type[BaseModel] = MultiIndicatorVoteInput

    def _run(self, vt_symbol: str, period_days: int = 120, indicators: list[str] | None = None) -> str:
        try:
            from datetime import datetime, timedelta
            from aqp.core.types import Symbol
            from aqp.data.duckdb_engine import DuckDBHistoryProvider
            from aqp.data.indicators_zoo import IndicatorZoo
            sym = Symbol.parse(vt_symbol)
            end = datetime.utcnow()
            start = end - timedelta(days=int(period_days * 1.6))
            bars = DuckDBHistoryProvider().get_bars(symbols=[sym], start=start, end=end)
            if bars is None or bars.empty:
                return json.dumps({"error": "no bars", "vt_symbol": vt_symbol})
            zoo = IndicatorZoo(indicators or ["SMA:20", "SMA:50", "EMA:12", "EMA:26", "RSI:14", "MACD"])
            result = zoo.transform(bars[bars["vt_symbol"] == vt_symbol])
            last = result.iloc[-1]
            close = float(last.get("close", float("nan")))
            bull, bear = 0, 0
            per_indicator = {}
            for col, val in last.items():
                if col in {"open", "high", "low", "close", "volume", "timestamp", "vt_symbol"}:
                    continue
                try:
                    v = float(val)
                except Exception:
                    continue
                if "RSI" in col:
                    if v < 30:
                        bull += 1; per_indicator[col] = "bull"
                    elif v > 70:
                        bear += 1; per_indicator[col] = "bear"
                    else:
                        per_indicator[col] = "neutral"
                elif "SMA" in col or "EMA" in col:
                    if close > v:
                        bull += 1; per_indicator[col] = "bull"
                    else:
                        bear += 1; per_indicator[col] = "bear"
            return json.dumps({
                "vt_symbol": vt_symbol, "bull_votes": bull, "bear_votes": bear,
                "per_indicator": per_indicator, "close": close,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("multi_indicator_vote_tool failed")
            return json.dumps({"error": str(exc), "vt_symbol": vt_symbol})


# ---------------------------------------------------------------------------
# Chart pattern detection
# ---------------------------------------------------------------------------


class ChartPatternInput(BaseModel):
    vt_symbol: str = Field(...)
    period_days: int = Field(default=180, ge=30, le=2520)
    swing_window: int = Field(default=5, ge=2, le=21)


class ChartPatternTool(BaseTool):
    name: str = "chart_pattern_tool"
    description: str = (
        "Detect double-top, double-bottom, head-and-shoulders, and inverse "
        "head-and-shoulders patterns over recent bars. Returns a list of detections "
        "with timestamps and scores."
    )
    args_schema: type[BaseModel] = ChartPatternInput

    def _run(self, vt_symbol: str, period_days: int = 180, swing_window: int = 5) -> str:
        try:
            from datetime import datetime, timedelta
            from aqp.core.types import Symbol
            from aqp.data.duckdb_engine import DuckDBHistoryProvider
            from aqp.data.patterns import detect_all
            sym = Symbol.parse(vt_symbol)
            end = datetime.utcnow()
            start = end - timedelta(days=int(period_days * 1.6))
            bars = DuckDBHistoryProvider().get_bars(symbols=[sym], start=start, end=end)
            if bars is None or bars.empty:
                return json.dumps({"error": "no bars", "vt_symbol": vt_symbol})
            sub = bars[bars["vt_symbol"] == vt_symbol].sort_values("timestamp").set_index("timestamp")["close"]
            detections = detect_all(sub, window=swing_window)
            return json.dumps({
                "vt_symbol": vt_symbol,
                "n_detections": len(detections),
                "patterns": [
                    {
                        "pattern": d.pattern, "timestamp": str(d.timestamp),
                        "score": d.score, "extras": {k: float(v) for k, v in d.extras.items()},
                    }
                    for d in detections[-20:]
                ],
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("chart_pattern_tool failed")
            return json.dumps({"error": str(exc), "vt_symbol": vt_symbol})


# ---------------------------------------------------------------------------
# Option Greeks (Bachelier + inverse)
# ---------------------------------------------------------------------------


class OptionGreeksInput(BaseModel):
    forward: float = Field(..., gt=0)
    strike: float = Field(..., gt=0)
    time_to_expiry_years: float = Field(..., gt=0)
    sigma: float = Field(..., gt=0)
    is_call: bool = True
    model: str = Field(default="bachelier", description="'bachelier' or 'inverse'")


class OptionGreeksTool(BaseTool):
    name: str = "option_greeks_tool"
    description: str = (
        "Compute option price + Greeks under either the Bachelier (normal) model "
        "or the inverse-option (Deribit-style, settled in BTC) model."
    )
    args_schema: type[BaseModel] = OptionGreeksInput

    def _run(self, forward: float, strike: float, time_to_expiry_years: float, sigma: float, is_call: bool = True, model: str = "bachelier") -> str:
        try:
            if model == "bachelier":
                from aqp.options.normal_model import bachelier_greeks
                g = bachelier_greeks(forward, strike, time_to_expiry_years, sigma, is_call=is_call)
                return json.dumps({
                    "model": "bachelier",
                    "price": g.price, "delta": g.delta, "gamma": g.gamma,
                    "theta": g.theta, "vega": g.vega, "vanna": g.vanna,
                    "volga": g.volga, "veta": g.veta,
                })
            elif model == "inverse":
                from aqp.options.inverse_options import inverse_greeks
                g = inverse_greeks(forward, strike, time_to_expiry_years, sigma, is_call=is_call)
                return json.dumps({
                    "model": "inverse",
                    "price_btc": g.price_btc, "price_usd": g.price_usd,
                    "delta_usd": g.delta_usd, "gamma_usd": g.gamma_usd,
                    "vega": g.vega, "theta": g.theta,
                })
            else:
                return json.dumps({"error": f"unknown model: {model}"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("option_greeks_tool failed")
            return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Option spread P&L
# ---------------------------------------------------------------------------


class OptionSpreadInput(BaseModel):
    long_strike: float = Field(..., gt=0)
    short_strike: float = Field(..., gt=0)
    long_premium: float = Field(..., ge=0)
    short_premium: float = Field(..., ge=0)
    is_call: bool = True


class OptionSpreadTool(BaseTool):
    name: str = "option_spread_tool"
    description: str = (
        "Compute vertical option spread P&L: max profit, max loss, breakeven, "
        "net debit/credit, mid value."
    )
    args_schema: type[BaseModel] = OptionSpreadInput

    def _run(self, long_strike: float, short_strike: float, long_premium: float, short_premium: float, is_call: bool = True) -> str:
        try:
            from aqp.options.spreads import vertical_spread
            v = vertical_spread(long_strike, short_strike, long_premium, short_premium, is_call=is_call)
            return json.dumps({
                "is_call": v.is_call, "width": v.width, "net_debit": v.net_debit,
                "max_profit": v.max_profit, "max_loss": v.max_loss,
                "breakeven": v.breakeven, "mid_value": v.mid_value,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("option_spread_tool failed")
            return json.dumps({"error": str(exc)})


__all__ = [
    "ChartPatternTool",
    "CointegrationTool",
    "FactorScreenTool",
    "HftMetricsTool",
    "MultiIndicatorVoteTool",
    "OptionGreeksTool",
    "OptionSpreadTool",
    "RealisedVolTool",
    "RegimeClassifierTool",
]
