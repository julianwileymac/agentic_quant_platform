"""High-level backtest orchestrator.

Takes a YAML config dict and:

1. Instantiates the strategy via ``build_from_config``.
2. Loads bars from the DuckDB history provider.
3. Dispatches to one of three interchangeable engines (event / vectorbt /
   backtesting.py) based on a ``backtest.engine`` key or the ``class``.
4. Persists a ``BacktestRun`` row + ledger entries + an MLflow run, and
   writes the resulting ``mlflow_run_id`` back onto the DB row so the
   Strategy Browser can deep-link into the experiment.

Engines share the :class:`aqp.backtest.engine.BacktestResult` output shape so
callers don't have to branch on engine type.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.config import settings
from aqp.core.registry import build_from_config, resolve
from aqp.core.types import Symbol
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.persistence.db import get_session
from aqp.persistence.models import BacktestRun

logger = logging.getLogger(__name__)


_ENGINE_SHORTCUTS: dict[str, tuple[str, str]] = {
    "event": ("EventDrivenBacktester", "aqp.backtest.engine"),
    "event-driven": ("EventDrivenBacktester", "aqp.backtest.engine"),
    "default": ("EventDrivenBacktester", "aqp.backtest.engine"),
    "vectorbt": ("VectorbtEngine", "aqp.backtest.vectorbt_engine"),
    "vbt": ("VectorbtEngine", "aqp.backtest.vectorbt_engine"),
    "backtesting": ("BacktestingPyEngine", "aqp.backtest.bt_engine"),
    "backtesting.py": ("BacktestingPyEngine", "aqp.backtest.bt_engine"),
    "bt": ("BacktestingPyEngine", "aqp.backtest.bt_engine"),
}


def _coerce_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def _symbols_from_strategy_cfg(strategy_cfg: dict[str, Any]) -> list[Symbol]:
    kwargs = strategy_cfg.get("kwargs", {})
    uni = kwargs.get("universe_model", {}).get("kwargs", {}) if isinstance(kwargs, dict) else {}
    tickers = _coerce_list(uni.get("symbols", [])) or settings.universe_list
    return [Symbol.parse(t) if "." in t else Symbol(ticker=t) for t in tickers]


def _resolve_backtest_cfg(backtest_cfg: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Pick the right engine class for the given config.

    Supports three shapes:
    - ``{engine: 'vectorbt', kwargs: {...}}`` — shortcut lookup.
    - ``{class: 'VectorbtEngine', kwargs: {...}}`` — explicit class.
    - ``{kwargs: {...}}`` — defaults to the event-driven engine.

    Returns a normalised config dict ready for ``build_from_config`` plus a
    string label for DB/MLflow tagging.
    """
    cfg = dict(backtest_cfg or {})
    engine_hint = cfg.pop("engine", None)
    if "class" in cfg:
        label = cfg["class"]
    elif engine_hint:
        key = str(engine_hint).lower().strip()
        if key not in _ENGINE_SHORTCUTS:
            raise ValueError(
                f"Unknown engine '{engine_hint}'. Options: {sorted(set(_ENGINE_SHORTCUTS))}"
            )
        cls_name, module_path = _ENGINE_SHORTCUTS[key]
        cfg = {"class": cls_name, "module_path": module_path, "kwargs": cfg.get("kwargs", {})}
        label = cls_name
    else:
        cfg = {
            "class": "EventDrivenBacktester",
            "module_path": "aqp.backtest.engine",
            "kwargs": cfg.get("kwargs", {}),
        }
        label = "EventDrivenBacktester"

    # Short names to human-friendly labels for metrics.
    label_map = {
        "EventDrivenBacktester": "event",
        "VectorbtEngine": "vectorbt",
        "BacktestingPyEngine": "backtesting",
    }
    return cfg, label_map.get(label, label)


def _strategy_slug(strategy_cfg: dict[str, Any]) -> str:
    cls = strategy_cfg.get("class") or "strategy"
    kwargs = strategy_cfg.get("kwargs", {}) or {}
    alpha = kwargs.get("alpha_model", {})
    alpha_cls = alpha.get("class") if isinstance(alpha, dict) else None
    candidate = alpha_cls or cls
    slug = re.sub(r"[^a-z0-9]+", "-", str(candidate).lower()).strip("-")
    return slug or "strategy"


def _deployment_id_from_strategy_cfg(strategy_cfg: dict[str, Any]) -> str | None:
    kwargs = strategy_cfg.get("kwargs", {}) if isinstance(strategy_cfg, dict) else {}
    alpha = kwargs.get("alpha_model", {}) if isinstance(kwargs, dict) else {}
    if not isinstance(alpha, dict):
        return None
    alpha_kwargs = alpha.get("kwargs", {})
    if not isinstance(alpha_kwargs, dict):
        return None
    deployment_id = alpha_kwargs.get("deployment_id")
    return str(deployment_id) if deployment_id else None


def _dataset_hash_for_deployment(deployment_id: str | None) -> str | None:
    if not deployment_id:
        return None
    try:
        from aqp.persistence.models import DatasetVersion, ModelDeployment, ModelVersion

        with get_session() as session:
            deployment = session.get(ModelDeployment, deployment_id)
            if deployment is None:
                return None
            if deployment.dataset_version_id:
                version = session.get(DatasetVersion, deployment.dataset_version_id)
                if version and version.dataset_hash:
                    return version.dataset_hash
            model_version = session.get(ModelVersion, deployment.model_version_id)
            return model_version.dataset_hash if model_version else None
    except Exception:
        logger.debug("could not resolve dataset hash for deployment %s", deployment_id, exc_info=True)
        return None


def run_backtest_from_config(
    cfg: dict[str, Any],
    run_name: str = "adhoc",
    persist: bool = True,
    mlflow_log: bool = True,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    strategy_cfg = cfg.get("strategy")
    backtest_cfg = cfg.get("backtest")
    if not strategy_cfg or not backtest_cfg:
        raise ValueError("config must have 'strategy' and 'backtest' blocks")

    strategy = build_from_config(strategy_cfg)
    engine_cfg, engine_label = _resolve_backtest_cfg(backtest_cfg)
    backtester = build_from_config(engine_cfg)

    start = pd.Timestamp(engine_cfg.get("kwargs", {}).get("start") or settings.default_start)
    end = pd.Timestamp(engine_cfg.get("kwargs", {}).get("end") or settings.default_end)

    provider = DuckDBHistoryProvider()
    symbols = _symbols_from_strategy_cfg(strategy_cfg)
    bars = provider.get_bars(symbols, start=start, end=end)
    if bars.empty:
        raise RuntimeError(
            f"No bars for {[s.vt_symbol for s in symbols]} between {start.date()} and {end.date()}. "
            f"Did you run `make ingest`?"
        )

    logger.info(
        "Running backtest '%s' [%s] on %d bars across %d symbols",
        run_name,
        engine_label,
        len(bars),
        bars["vt_symbol"].nunique(),
    )
    result = backtester.run(strategy, bars)

    summary = result.summary
    summary["engine"] = engine_label
    deployment_id = _deployment_id_from_strategy_cfg(strategy_cfg)
    if deployment_id:
        summary["model_deployment_id"] = deployment_id
    dataset_hash = _dataset_hash_for_deployment(deployment_id)
    equity_dict = {str(idx): float(v) for idx, v in result.equity_curve.items()}

    mlflow_run_id: str | None = None
    if mlflow_log:
        try:
            from aqp.mlops.mlflow_client import log_backtest

            mlflow_run_id = log_backtest(
                run_name=run_name,
                summary=summary,
                strategy_cfg=strategy_cfg,
                equity_curve=result.equity_curve,
                dataset_hash=dataset_hash,
                strategy_id=strategy_id,
                engine=engine_label,
            )
        except Exception as e:
            logger.warning("MLflow logging skipped: %s", e)

    row_id: str | None = None
    if persist:
        row_id = _persist_run(
            run_name=run_name,
            summary=summary,
            result=result,
            strategy_cfg=strategy_cfg,
            equity_dict=equity_dict,
            mlflow_run_id=mlflow_run_id,
            engine_label=engine_label,
            dataset_hash=dataset_hash,
            strategy_id=strategy_id,
        )

    return {
        "run_id": row_id,
        "mlflow_run_id": mlflow_run_id,
        "run_name": run_name,
        "engine": engine_label,
        "model_deployment_id": deployment_id,
        "dataset_hash": dataset_hash,
        "sharpe": summary.get("sharpe"),
        "sortino": summary.get("sortino"),
        "max_drawdown": summary.get("max_drawdown"),
        "total_return": summary.get("total_return"),
        "final_equity": summary.get("final_equity"),
        "start": str(result.start),
        "end": str(result.end),
        "n_trades": summary.get("n_trades", len(result.trades)),
    }


def _persist_run(
    run_name: str,
    summary: dict[str, Any],
    result,
    strategy_cfg: dict[str, Any],
    equity_dict: dict[str, float],
    mlflow_run_id: str | None = None,
    engine_label: str | None = None,
    dataset_hash: str | None = None,
    strategy_id: str | None = None,
) -> str:
    row = BacktestRun(
        strategy_id=strategy_id,
        status="completed",
        start=result.start,
        end=result.end,
        initial_cash=result.initial_cash,
        final_equity=result.final_equity,
        sharpe=summary.get("sharpe"),
        sortino=summary.get("sortino"),
        max_drawdown=summary.get("max_drawdown"),
        total_return=summary.get("total_return"),
        mlflow_run_id=mlflow_run_id,
        dataset_hash=dataset_hash,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        metrics={
            **summary,
            "equity_curve": equity_dict,
            "run_name": run_name,
            "strategy_config": strategy_cfg,
            "engine": engine_label,
        },
    )
    try:
        with get_session() as session:
            session.add(row)
            session.flush()
            return row.id
    except Exception as e:
        logger.warning("Backtest persistence skipped (DB unavailable): %s", e)
        return ""


def build_engine(shortcut_or_config: str | dict[str, Any]):
    """Resolve an engine from a shortcut label or full config. Handy helper
    for tasks / REPL users who want to bypass YAML."""
    if isinstance(shortcut_or_config, str):
        key = shortcut_or_config.lower()
        if key not in _ENGINE_SHORTCUTS:
            raise KeyError(f"Unknown engine '{shortcut_or_config}'")
        cls_name, module_path = _ENGINE_SHORTCUTS[key]
        cls = resolve(cls_name, module_path)
        return cls()
    return build_from_config(shortcut_or_config)
