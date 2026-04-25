"""Performance metrics + Plotly chart tools for the Evaluator."""
from __future__ import annotations

import json
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MetricsInput(BaseModel):
    backtest_id: str = Field(..., description="The backtest_runs.id to summarise.")


class MetricsTool(BaseTool):
    name: str = "metrics"
    description: str = (
        "Fetch Sharpe, Sortino, MaxDD, Calmar, total_return, and turnover for a backtest. "
        "Returns a JSON object."
    )
    args_schema: type[BaseModel] = MetricsInput

    def _run(self, backtest_id: str) -> str:  # type: ignore[override]
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import BacktestRun

        with get_session() as session:
            row = session.execute(
                select(BacktestRun).where(BacktestRun.id == backtest_id)
            ).scalar_one_or_none()
            if row is None:
                return f"No backtest with id {backtest_id}"
            payload = {
                "id": row.id,
                "strategy_id": row.strategy_id,
                "sharpe": row.sharpe,
                "sortino": row.sortino,
                "max_drawdown": row.max_drawdown,
                "total_return": row.total_return,
                "final_equity": row.final_equity,
                "start": str(row.start),
                "end": str(row.end),
                "status": row.status,
                "metrics": row.metrics or {},
                "mlflow_run_id": row.mlflow_run_id,
            }
        return json.dumps(payload, default=str, indent=2)


class PlotlyInput(BaseModel):
    backtest_id: str
    kind: str = Field(default="equity", description="equity | drawdown | returns")


class PlotlyTool(BaseTool):
    name: str = "plotly"
    description: str = (
        "Produce a Plotly JSON figure for a completed backtest. Kinds: equity, drawdown, returns."
    )
    args_schema: type[BaseModel] = PlotlyInput

    def _run(self, backtest_id: str, kind: str = "equity") -> str:  # type: ignore[override]
        from aqp.backtest.metrics import plot_drawdown, plot_equity_curve, plot_returns_histogram

        try:
            if kind == "equity":
                fig = plot_equity_curve(backtest_id)
            elif kind == "drawdown":
                fig = plot_drawdown(backtest_id)
            elif kind == "returns":
                fig = plot_returns_histogram(backtest_id)
            else:
                return f"Unknown kind {kind!r}. Expected equity|drawdown|returns."
        except Exception as e:
            logger.exception("Plotly tool failed")
            return f"ERROR: {e}"
        return fig.to_json()
