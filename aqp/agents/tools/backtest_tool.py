"""Backtest tool — triggers the event-driven engine and WFO from inside an agent."""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from itertools import product
from typing import Any

import yaml
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BacktestInput(BaseModel):
    config_yaml: str = Field(..., description="Inline YAML describing the strategy + backtest.")
    name: str = Field(default="adhoc", description="A friendly name for the run.")
    engine: str | None = Field(
        default=None,
        description="Optional engine override, e.g. vectorbt-pro, vectorbt, event, bt, or fallback.",
    )
    fallback_engines: list[str] | None = Field(
        default=None,
        description="Optional fallback engine list used when engine='fallback'.",
    )


class BacktestTool(BaseTool):
    name: str = "backtest"
    description: str = (
        "Run an end-to-end backtest from an inline YAML config. The config should match "
        "configs/strategies/*.yaml schema (strategy + backtest blocks). Returns a JSON summary "
        "with Sharpe, Sortino, MaxDD, total_return, and the MLflow run_id."
    )
    args_schema: type[BaseModel] = BacktestInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        name: str = "adhoc",
        engine: str | None = None,
        fallback_engines: list[str] | None = None,
    ) -> str:
        from aqp.backtest.runner import run_backtest_from_config

        try:
            cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return f"ERROR: invalid YAML — {e}"
        backtest_cfg = cfg.get("backtest", {}) if isinstance(cfg, dict) else {}
        if engine is None and "engine" not in backtest_cfg and "class" not in backtest_cfg:
            engine = "vectorbt-pro"
        cfg = _apply_engine_override(cfg, engine=engine, fallback_engines=fallback_engines)
        try:
            result = run_backtest_from_config(cfg, run_name=name)
        except Exception as e:
            logger.exception("Backtest failed")
            return f"ERROR: {e}"
        return json.dumps(result, default=str, indent=2)


class EngineCompareInput(BaseModel):
    config_yaml: str
    engines: list[str] = Field(default_factory=lambda: ["vectorbt-pro", "vectorbt", "event"])
    name: str = "compare"


class EngineCompareTool(BaseTool):
    name: str = "backtest_compare"
    description: str = (
        "Run the same strategy config through multiple engines and return normalized metrics. "
        "Useful for comparing vectorbt Pro research speed with event-engine fidelity."
    )
    args_schema: type[BaseModel] = EngineCompareInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        engines: list[str] | None = None,
        name: str = "compare",
    ) -> str:
        from aqp.backtest.runner import run_backtest_from_config

        try:
            base_cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return f"ERROR: invalid YAML — {e}"
        out: dict[str, Any] = {}
        for engine in engines or ["vectorbt-pro", "vectorbt", "event"]:
            cfg = _apply_engine_override(deepcopy(base_cfg), engine=engine)
            try:
                out[engine] = run_backtest_from_config(
                    cfg,
                    run_name=f"{name}-{engine}",
                    persist=False,
                    mlflow_log=False,
                )
            except Exception as exc:
                logger.exception("Engine comparison failed for %s", engine)
                out[engine] = {"error": str(exc)}
        return json.dumps(out, default=str, indent=2)


class VectorbtSweepInput(BaseModel):
    config_yaml: str
    parameter_grid: dict[str, list[Any]] = Field(
        ...,
        description=(
            "Strategy kwargs grid, e.g. {'fast': [5, 10], 'slow': [20, 50]}. "
            "Nested alpha kwargs can use dot paths such as 'alpha_model.kwargs.fast'."
        ),
    )
    engine: str = "vectorbt-pro"
    name: str = "vbt-sweep"
    max_runs: int = 25


class VectorbtSweepTool(BaseTool):
    name: str = "vectorbt_sweep"
    description: str = (
        "Run a small vectorbt Pro/vectorbt parameter sweep from an inline YAML config. "
        "Returns one normalized summary per parameter combination."
    )
    args_schema: type[BaseModel] = VectorbtSweepInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        parameter_grid: dict[str, list[Any]],
        engine: str = "vectorbt-pro",
        name: str = "vbt-sweep",
        max_runs: int = 25,
    ) -> str:
        from aqp.backtest.runner import run_backtest_from_config

        try:
            base_cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return f"ERROR: invalid YAML — {e}"
        keys = list(parameter_grid)
        combos = list(product(*[parameter_grid[key] for key in keys]))[: int(max_runs)]
        rows: list[dict[str, Any]] = []
        for i, values in enumerate(combos):
            cfg = _apply_engine_override(deepcopy(base_cfg), engine=engine)
            params = dict(zip(keys, values, strict=True))
            for path, value in params.items():
                _set_strategy_kwarg(cfg, path, value)
            try:
                result = run_backtest_from_config(
                    cfg,
                    run_name=f"{name}-{i}",
                    persist=False,
                    mlflow_log=False,
                )
                rows.append({"params": params, **result})
            except Exception as exc:
                rows.append({"params": params, "error": str(exc)})
        return json.dumps(rows, default=str, indent=2)


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


def _apply_engine_override(
    cfg: dict[str, Any],
    *,
    engine: str | None = None,
    fallback_engines: list[str] | None = None,
) -> dict[str, Any]:
    if engine is None and not fallback_engines:
        return cfg
    backtest = cfg.setdefault("backtest", {})
    if engine:
        backtest["engine"] = engine
    if fallback_engines:
        backtest["engine"] = "fallback"
        backtest["fallbacks"] = list(fallback_engines)
        backtest.setdefault("primary", engine or "vectorbt-pro")
    return cfg


def _set_strategy_kwarg(cfg: dict[str, Any], path: str, value: Any) -> None:
    kwargs = cfg.setdefault("strategy", {}).setdefault("kwargs", {})
    parts = path.split(".")
    target = kwargs
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
