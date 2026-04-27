"""Backtrader-backed agent tool.

Adapted from `FinRobot
<https://github.com/AI4Finance-Foundation/FinRobot>`_'s
``BackTraderUtils.back_test`` to fit AQP's CrewAI tool surface. Runs a
single-ticker backtest against yfinance bars (or AQP's local bars when
available) using the ``backtrader`` library.

This is intentionally a *complement* to :class:`BacktestTool`: that one
executes the platform's full multi-engine, multi-symbol pipeline; this
one is a quick "agent-callable single-ticker sanity check" that fits in
a single LLM context window.
"""
from __future__ import annotations

import importlib
import json
import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BacktraderInput(BaseModel):
    ticker_symbol: str = Field(..., description="Ticker, e.g. 'AAPL'.")
    start_date: str = Field(..., description="YYYY-MM-DD.")
    end_date: str = Field(..., description="YYYY-MM-DD.")
    strategy: str = Field(
        default="SMA_CrossOver",
        description=(
            "Either a built-in alias ('SMA_CrossOver') or 'module.path:ClassName' for a "
            "custom Backtrader strategy."
        ),
    )
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    sizer: int | str | None = Field(
        default=None,
        description="Fixed integer stake or 'module.path:ClassName' for a custom Sizer.",
    )
    sizer_params: dict[str, Any] = Field(default_factory=dict)
    cash: float = Field(default=10_000.0)


def _resolve_class(qualname: str) -> type:
    if ":" not in qualname:
        raise ValueError(f"expected 'module.path:ClassName', got {qualname!r}")
    module_path, class_name = qualname.split(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class BacktraderTool(BaseTool):
    name: str = "backtrader_quick"
    description: str = (
        "Quick single-ticker Backtrader backtest. Returns Sharpe, drawdown, returns, and "
        "trade analysis as a JSON summary. Useful for agent sanity checks before a full "
        "platform backtest."
    )
    args_schema: type[BaseModel] = BacktraderInput

    def _run(  # type: ignore[override]
        self,
        ticker_symbol: str,
        start_date: str,
        end_date: str,
        strategy: str = "SMA_CrossOver",
        strategy_params: dict[str, Any] | None = None,
        sizer: int | str | None = None,
        sizer_params: dict[str, Any] | None = None,
        cash: float = 10_000.0,
    ) -> str:
        try:
            import backtrader as bt
            import yfinance as yf
            from backtrader.strategies import SMA_CrossOver
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {
                    "error": f"backtrader/yfinance not available: {exc}",
                    "hint": "pip install backtrader yfinance",
                },
                indent=2,
            )

        cerebro = bt.Cerebro()

        if strategy == "SMA_CrossOver":
            strat_class = SMA_CrossOver
        else:
            try:
                strat_class = _resolve_class(strategy)
            except Exception as exc:  # noqa: BLE001
                return json.dumps({"error": f"could not resolve strategy: {exc}"}, indent=2)
        cerebro.addstrategy(strat_class, **(strategy_params or {}))

        try:
            df = yf.download(ticker_symbol, start_date, end_date, auto_adjust=True, progress=False)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"yfinance download failed: {exc}"}, indent=2)
        if df is None or df.empty:
            return json.dumps({"error": f"no bars for {ticker_symbol} in {start_date}..{end_date}"}, indent=2)

        cerebro.adddata(bt.feeds.PandasData(dataname=df))
        cerebro.broker.setcash(cash)

        if sizer is not None:
            try:
                if isinstance(sizer, int):
                    cerebro.addsizer(bt.sizers.FixedSize, stake=int(sizer))
                else:
                    sizer_class = _resolve_class(str(sizer))
                    cerebro.addsizer(sizer_class, **(sizer_params or {}))
            except Exception as exc:  # noqa: BLE001
                return json.dumps({"error": f"could not configure sizer: {exc}"}, indent=2)

        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_ratio")
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="draw_down")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_analyzer")

        starting_value = float(cerebro.broker.getvalue())
        try:
            results = cerebro.run()
        except Exception as exc:  # noqa: BLE001
            logger.exception("backtrader run failed")
            return json.dumps({"error": f"backtrader run failed: {exc}"}, indent=2)
        first = results[0]

        out: dict[str, Any] = {
            "ticker": ticker_symbol,
            "starting_value": starting_value,
            "final_value": float(cerebro.broker.getvalue()),
            "sharpe_ratio": dict(first.analyzers.sharpe_ratio.get_analysis() or {}),
            "drawdown": dict(first.analyzers.draw_down.get_analysis() or {}),
            "returns": dict(first.analyzers.returns.get_analysis() or {}),
        }
        try:
            out["trade_analyzer"] = dict(first.analyzers.trade_analyzer.get_analysis() or {})
        except Exception:  # noqa: BLE001
            out["trade_analyzer"] = {}
        return json.dumps(out, default=str, indent=2)
