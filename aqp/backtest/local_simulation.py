"""Local-drive backtest simulation.

Runs the same ``EventDrivenBacktester`` used everywhere else, but points
it at CSV or Parquet files on a mounted drive instead of the canonical
Parquet lake. The heavy lifting lives in the existing
``LocalCSVSource`` / ``LocalParquetSource`` adapters — this module just
glues them to the backtest pipeline so ``aqp backtest simulate
--local-path ...`` "just works".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.backtest.engine import BacktestResult, EventDrivenBacktester
from aqp.backtest.metrics import summarise
from aqp.core.interfaces import IStrategy
from aqp.data.ingestion import LocalCSVSource, LocalParquetSource

logger = logging.getLogger(__name__)


@dataclass
class LocalSimulator:
    """Run a strategy against CSV/Parquet files in a local directory."""

    source_path: str | Path
    format: str = "csv"
    glob: str | None = None
    column_map: dict[str, str] | None = None
    tz: str | None = None

    def load_bars(self) -> pd.DataFrame:
        if self.format.lower() == "csv":
            source = LocalCSVSource(
                root=self.source_path,
                glob=self.glob or "*.csv",
                column_map=self.column_map,
                tz=self.tz,
            )
        elif self.format.lower() in {"parquet", "pq"}:
            source = LocalParquetSource(
                root=self.source_path,
                glob=self.glob or "*.parquet",
                column_map=self.column_map,
                tz=self.tz,
            )
        else:
            raise ValueError(f"unsupported format: {self.format!r}")
        df = source.fetch()
        if df.empty:
            raise RuntimeError(f"no bars found under {self.source_path!r}")
        return df

    def run(
        self,
        strategy: IStrategy,
        start: str | None = None,
        end: str | None = None,
        initial_cash: float = 100000.0,
        commission_pct: float = 0.0005,
        slippage_bps: float = 2.0,
    ) -> BacktestResult:
        bars = self.load_bars()
        engine = EventDrivenBacktester(
            initial_cash=initial_cash,
            commission_pct=commission_pct,
            slippage_bps=slippage_bps,
            start=start,
            end=end,
        )
        return engine.run(strategy, bars)

    def run_with_summary(
        self,
        strategy: IStrategy,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = self.run(strategy, **kwargs)
        return {
            "summary": summarise(result.equity_curve, result.trades),
            "final_equity": result.final_equity,
            "initial_cash": result.initial_cash,
            "bar_count": len(result.equity_curve),
        }
