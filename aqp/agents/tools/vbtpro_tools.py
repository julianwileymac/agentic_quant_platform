"""Agent tools that surface the deep vbt-pro engine to crews.

Six tools shipped:

- :class:`VectorbtProBacktestTool` (``vectorbt_pro_backtest``) — single
  backtest, exposes ``mode`` (signals/orders/optimizer/holding/random).
- :class:`VbtProParamSweepTool` (``vectorbt_pro_param_sweep``) — grid sweep
  over strategy kwargs.
- :class:`VbtProWalkForwardTool` (``vectorbt_pro_wfo``) — Splitter-based
  WFO; supports per-window agent dispatch.
- :class:`VbtProOptimizerTool` (``vectorbt_pro_optimizer``) — runs an
  allocation-driven backtest using a registered ``PortfolioOptimizer``.
- :class:`EngineCapabilitiesTool` (``engine_capabilities``) — surfaces the
  capability matrix so an agent can choose an engine intelligently.
- :class:`AgentAwareBacktestTool` (``agent_aware_backtest``) — convenience
  for running a strategy that consults a named agent spec on every bar
  (event-driven path).
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

import yaml
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# vectorbt_pro_backtest
# ---------------------------------------------------------------------------


class VbtProBacktestInput(BaseModel):
    config_yaml: str = Field(..., description="Inline YAML strategy + backtest config.")
    mode: str = Field(
        default="signals",
        description="vbt-pro mode: signals, orders, optimizer, holding, random.",
    )
    name: str = Field(default="vbtpro-adhoc")
    persist: bool = Field(default=False, description="Persist results in DB / MLflow.")


class VectorbtProBacktestTool(BaseTool):
    name: str = "vectorbt_pro_backtest"
    description: str = (
        "Run a single vbt-pro backtest with explicit mode (signals/orders/optimizer/"
        "holding/random). Returns a JSON summary with vbt_* native stats."
    )
    args_schema: type[BaseModel] = VbtProBacktestInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        mode: str = "signals",
        name: str = "vbtpro-adhoc",
        persist: bool = False,
    ) -> str:
        from aqp.backtest.runner import run_backtest_from_config

        try:
            cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as exc:
            return f"ERROR: invalid YAML — {exc}"
        cfg = _force_vbtpro_mode(cfg, mode)
        try:
            result = run_backtest_from_config(
                cfg,
                run_name=name,
                persist=persist,
                mlflow_log=persist,
            )
        except Exception as exc:
            logger.exception("vectorbt_pro_backtest failed")
            return f"ERROR: {exc}"
        return json.dumps(result, default=str, indent=2)


# ---------------------------------------------------------------------------
# vectorbt_pro_param_sweep
# ---------------------------------------------------------------------------


class VbtProParamSweepInput(BaseModel):
    config_yaml: str
    parameter_grid: dict[str, list[Any]] = Field(
        ...,
        description=(
            "Dotted-key grid over strategy.kwargs (e.g. "
            "{'alpha_model.kwargs.fast': [5,10], 'alpha_model.kwargs.slow': [20,50]})."
        ),
    )
    metric: str = Field(default="sharpe", description="Metric to rank by.")
    method: str = Field(default="grid", description="grid or random.")
    n_trials: int | None = Field(default=None, description="Required when method=random.")
    name: str = Field(default="vbtpro-sweep")


class VbtProParamSweepTool(BaseTool):
    name: str = "vectorbt_pro_param_sweep"
    description: str = (
        "Grid or random sweep over strategy kwargs using the vbt-pro engine. Each "
        "trial is a fresh backtest. Returns a ranked frame plus the best combo."
    )
    args_schema: type[BaseModel] = VbtProParamSweepInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        parameter_grid: dict[str, list[Any]],
        metric: str = "sharpe",
        method: str = "grid",
        n_trials: int | None = None,
        name: str = "vbtpro-sweep",
    ) -> str:
        from aqp.backtest.vbtpro.param_sweep import sweep_strategy_kwargs

        try:
            base_cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as exc:
            return f"ERROR: invalid YAML — {exc}"

        try:
            result = sweep_strategy_kwargs(
                base_cfg,
                parameter_grid,
                metric=metric,
                method=method,
                n_trials=n_trials,
            )
        except Exception as exc:
            logger.exception("vectorbt_pro_param_sweep failed")
            return f"ERROR: {exc}"
        return json.dumps(
            {
                "metric": result.metric,
                "best_combo": result.best_combo,
                "best_value": result.best_value,
                "rows": result.frame.head(50).to_dict(orient="records"),
            },
            default=str,
            indent=2,
        )


# ---------------------------------------------------------------------------
# vectorbt_pro_wfo
# ---------------------------------------------------------------------------


class VbtProWfoInput(BaseModel):
    config_yaml: str
    splitter: str = Field(default="rolling", description="rolling, expanding, or purged.")
    n_splits: int = 5
    train_size: int | None = None
    test_size: int | None = None
    embargo: int | None = None
    name: str = Field(default="vbtpro-wfo")


class VbtProWalkForwardTool(BaseTool):
    name: str = "vectorbt_pro_wfo"
    description: str = (
        "Walk-forward optimisation built on vbt-pro's Splitter. Per-window train + "
        "test backtests; supports purged WFO. Re-instantiates the strategy per "
        "window so agents/ML can refit between splits."
    )
    args_schema: type[BaseModel] = VbtProWfoInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        splitter: str = "rolling",
        n_splits: int = 5,
        train_size: int | None = None,
        test_size: int | None = None,
        embargo: int | None = None,
        name: str = "vbtpro-wfo",
    ) -> str:
        from aqp.backtest.runner import _load_bars, _symbols_from_strategy_cfg
        from aqp.backtest.vbtpro.wfo import WalkForwardHarness
        from aqp.config import settings
        import pandas as pd

        try:
            cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as exc:
            return f"ERROR: invalid YAML — {exc}"

        strategy_cfg = cfg.get("strategy")
        if not strategy_cfg:
            return "ERROR: config must include a `strategy:` block"

        try:
            start = pd.Timestamp(
                cfg.get("backtest", {}).get("kwargs", {}).get("start") or settings.default_start
            )
            end = pd.Timestamp(
                cfg.get("backtest", {}).get("kwargs", {}).get("end") or settings.default_end
            )
            bars, _ = _load_bars(strategy_cfg, cfg, start=start, end=end)
        except Exception as exc:
            return f"ERROR loading bars: {exc}"

        try:
            harness = WalkForwardHarness(
                strategy_cfg,
                splitter=splitter,
                n_splits=n_splits,
                train_size=train_size,
                test_size=test_size,
                embargo=embargo,
                engine_kwargs=cfg.get("backtest", {}).get("kwargs", {}),
            )
            wfo = harness.run(bars)
        except Exception as exc:
            logger.exception("vectorbt_pro_wfo failed")
            return f"ERROR: {exc}"

        out = {
            "summary": wfo.summary,
            "n_windows": len(wfo.windows),
            "windows": [
                {
                    "window_index": w.window_index,
                    "train_start": str(w.train_start),
                    "train_end": str(w.train_end),
                    "test_start": str(w.test_start),
                    "test_end": str(w.test_end),
                    "test_summary": w.test_summary,
                }
                for w in wfo.windows
            ],
        }
        return json.dumps(out, default=str, indent=2)


# ---------------------------------------------------------------------------
# vectorbt_pro_optimizer
# ---------------------------------------------------------------------------


class VbtProOptimizerInput(BaseModel):
    config_yaml: str
    optimizer: dict[str, Any] = Field(
        ...,
        description=(
            "Build-spec for an allocator class (one of EqualWeightOptimizer, "
            "RandomWeightOptimizer, MeanVarianceOptimizer, CallableOptimizer)."
        ),
    )
    name: str = Field(default="vbtpro-opt")


class VbtProOptimizerTool(BaseTool):
    name: str = "vectorbt_pro_optimizer"
    description: str = (
        "Run an allocation-driven backtest via Portfolio.from_optimizer. The "
        "`optimizer` arg is a class/module_path/kwargs build-spec (e.g. "
        "{class: MeanVarianceOptimizer, module_path: aqp.backtest.vbtpro.optimizer_adapter})."
    )
    args_schema: type[BaseModel] = VbtProOptimizerInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        optimizer: dict[str, Any],
        name: str = "vbtpro-opt",
    ) -> str:
        from aqp.backtest.runner import run_backtest_from_config

        try:
            cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as exc:
            return f"ERROR: invalid YAML — {exc}"

        bt_cfg = cfg.setdefault("backtest", {})
        bt_cfg["engine"] = "vbt-pro:optimizer"
        bt_cfg.setdefault("kwargs", {})["optimizer"] = optimizer
        try:
            result = run_backtest_from_config(
                cfg,
                run_name=name,
                persist=False,
                mlflow_log=False,
            )
        except Exception as exc:
            logger.exception("vectorbt_pro_optimizer failed")
            return f"ERROR: {exc}"
        return json.dumps(result, default=str, indent=2)


# ---------------------------------------------------------------------------
# engine_capabilities
# ---------------------------------------------------------------------------


class EngineCapabilitiesInput(BaseModel):
    engine: str | None = Field(
        default=None,
        description=(
            "Optional engine name (e.g. 'VectorbtProEngine', 'EventDrivenBacktester'). "
            "When omitted returns the full capability matrix."
        ),
    )


class EngineCapabilitiesTool(BaseTool):
    name: str = "engine_capabilities"
    description: str = (
        "Inspect the capability surface of registered backtest engines. Returns "
        "a feature matrix (signals, orders, callbacks, multi_asset, lob, async, "
        "license, requires_optional_dep, ...). Use this to pick an engine."
    )
    args_schema: type[BaseModel] = EngineCapabilitiesInput

    def _run(  # type: ignore[override]
        self,
        engine: str | None = None,
    ) -> str:
        from aqp.backtest.base import engine_capabilities_index

        idx = engine_capabilities_index()
        if engine is not None:
            cap = idx.get(engine)
            if cap is None:
                return f"ERROR: engine {engine!r} not found. Known: {sorted(idx)}"
            return json.dumps(cap.to_dict(), default=str, indent=2)
        return json.dumps(
            {name: cap.to_dict() for name, cap in idx.items()},
            default=str,
            indent=2,
        )


# ---------------------------------------------------------------------------
# agent_aware_backtest
# ---------------------------------------------------------------------------


class AgentAwareBacktestInput(BaseModel):
    config_yaml: str = Field(..., description="Strategy + backtest config.")
    agent_spec: str = Field(
        ...,
        description="Name of the AgentSpec to consult on every bar.",
    )
    lookback_bars: int = Field(default=20)
    momentum_threshold: float = Field(default=0.02)
    min_agent_confidence: float = Field(default=0.6)
    name: str = Field(default="agent-aware-backtest")


class AgentAwareBacktestTool(BaseTool):
    name: str = "agent_aware_backtest"
    description: str = (
        "Run a backtest where every bar consults a named AgentSpec via the per-bar "
        "AgentDispatcher. Uses the AgentAwareMomentumAlpha as a worked example "
        "and routes through the event-driven engine (vbt-pro per-bar callbacks "
        "are Numba-only)."
    )
    args_schema: type[BaseModel] = AgentAwareBacktestInput

    def _run(  # type: ignore[override]
        self,
        config_yaml: str,
        agent_spec: str,
        lookback_bars: int = 20,
        momentum_threshold: float = 0.02,
        min_agent_confidence: float = 0.6,
        name: str = "agent-aware-backtest",
    ) -> str:
        from aqp.backtest.runner import run_backtest_from_config

        try:
            cfg = yaml.safe_load(config_yaml)
        except yaml.YAMLError as exc:
            return f"ERROR: invalid YAML — {exc}"

        cfg = deepcopy(cfg)
        strategy_cfg = cfg.setdefault("strategy", {})
        kwargs = strategy_cfg.setdefault("kwargs", {})
        kwargs["alpha_model"] = {
            "class": "AgentAwareMomentumAlpha",
            "module_path": "aqp.strategies.agentic.agent_aware_alpha",
            "kwargs": {
                "spec_name": agent_spec,
                "lookback_bars": lookback_bars,
                "momentum_threshold": momentum_threshold,
                "min_agent_confidence": min_agent_confidence,
            },
        }
        # Force the event-driven engine — vbt-pro callbacks are Numba-only.
        cfg.setdefault("backtest", {})["engine"] = "event"

        try:
            result = run_backtest_from_config(cfg, run_name=name, persist=False, mlflow_log=False)
        except Exception as exc:
            logger.exception("agent_aware_backtest failed")
            return f"ERROR: {exc}"
        return json.dumps(result, default=str, indent=2)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _force_vbtpro_mode(cfg: dict[str, Any], mode: str) -> dict[str, Any]:
    out = deepcopy(cfg)
    bt_cfg = out.setdefault("backtest", {})
    bt_cfg["engine"] = f"vbt-pro:{mode}" if mode != "signals" else "vbt-pro"
    return out


__all__ = [
    "VectorbtProBacktestTool",
    "VbtProParamSweepTool",
    "VbtProWalkForwardTool",
    "VbtProOptimizerTool",
    "EngineCapabilitiesTool",
    "AgentAwareBacktestTool",
]
