"""Backtest tool — triggers the event-driven engine and WFO from inside an agent."""
from __future__ import annotations

import json
import logging

import yaml
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BacktestInput(BaseModel):
    config_yaml: str = Field(..., description="Inline YAML describing the strategy + backtest.")
    name: str = Field(default="adhoc", description="A friendly name for the run.")


class BacktestTool(BaseTool):
    name: str = "backtest"
    description: str = (
        "Run an end-to-end backtest from an inline YAML config. The config should match "
        "configs/strategies/*.yaml schema (strategy + backtest blocks). Returns a JSON summary "
        "with Sharpe, Sortino, MaxDD, total_return, and the MLflow run_id."
    )
    args_schema: type[BaseModel] = BacktestInput

    def _run(self, config_yaml: str, name: str = "adhoc") -> str:  # type: ignore[override]
        from aqp.backtest.runner import run_backtest_from_config

        try:
            cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return f"ERROR: invalid YAML — {e}"
        try:
            result = run_backtest_from_config(cfg, run_name=name)
        except Exception as e:
            logger.exception("Backtest failed")
            return f"ERROR: {e}"
        return json.dumps(result, default=str, indent=2)


class WalkForwardInput(BaseModel):
    config_yaml: str
    train_window_days: int = 252
    test_window_days: int = 63
    step_days: int = 63


class WalkForwardTool(BaseTool):
    name: str = "walk_forward"
    description: str = (
        "Run Walk-Forward Optimization across rolling windows. Returns aggregated out-of-sample "
        "Sharpe and a list of per-window metrics."
    )
    args_schema: type[BaseModel] = WalkForwardInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        train_window_days: int = 252,
        test_window_days: int = 63,
        step_days: int = 63,
    ) -> str:
        from aqp.backtest.walk_forward import run_walk_forward

        try:
            cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return f"ERROR: invalid YAML — {e}"
        try:
            result = run_walk_forward(
                cfg,
                train_window_days=train_window_days,
                test_window_days=test_window_days,
                step_days=step_days,
            )
        except Exception as e:
            logger.exception("WFO failed")
            return f"ERROR: {e}"
        return json.dumps(result, default=str, indent=2)
