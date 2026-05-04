"""High-level backtest orchestrator.

Takes a YAML config dict and:

1. Instantiates the strategy via ``build_from_config``.
2. Loads bars from the DuckDB history provider.
3. Dispatches to interchangeable engines (event / vectorbt Pro / vectorbt /
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
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.config import settings
from aqp.core.registry import build_from_config, resolve
from aqp.core.types import Symbol
from aqp.data import iceberg_catalog
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.persistence.db import get_session
from aqp.persistence.models import BacktestRun

logger = logging.getLogger(__name__)


_ENGINE_SHORTCUTS: dict[str, tuple[str, str]] = {
    # Event-driven (per-bar Python; preserved for backward compatibility and
    # for true async agent dispatch).
    "event": ("EventDrivenBacktester", "aqp.backtest.engine"),
    "event-driven": ("EventDrivenBacktester", "aqp.backtest.engine"),
    "default": ("EventDrivenBacktester", "aqp.backtest.engine"),
    # vectorbt-pro (primary vectorised engine; multi-mode).
    "vectorbt-pro": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "vbt-pro": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "vectorbtpro": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "vbtpro": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "primary": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    # Mode-specific shortcuts — pick the right vbt-pro constructor.
    "vbt-pro:signals": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "vbt-pro:orders": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "vbt-pro:optimizer": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "vbt-pro:holding": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    "vbt-pro:random": ("VectorbtProEngine", "aqp.backtest.vectorbtpro_engine"),
    # OSS vectorbt fallback.
    "vectorbt": ("VectorbtEngine", "aqp.backtest.vectorbt_engine"),
    "vbt": ("VectorbtEngine", "aqp.backtest.vectorbt_engine"),
    # Fallback cascade.
    "fallback": ("FallbackBacktestEngine", "aqp.backtest.fallback_engine"),
    "cascade": ("FallbackBacktestEngine", "aqp.backtest.fallback_engine"),
    # backtesting.py single-symbol path.
    "backtesting": ("BacktestingPyEngine", "aqp.backtest.bt_engine"),
    "backtesting.py": ("BacktestingPyEngine", "aqp.backtest.bt_engine"),
    "bt": ("BacktestingPyEngine", "aqp.backtest.bt_engine"),
    # Permissive-licence fallback adapters (lazy imports).
    "zvt": ("ZvtBacktestEngine", "aqp.backtest.zvt_engine"),
    "aat": ("AatBacktestEngine", "aqp.backtest.aat_engine"),
}


# Mode-suffixed shortcuts inject ``mode=...`` into the engine kwargs so the
# user can pick a vbt-pro constructor without writing the full kwargs block.
_MODE_INJECTIONS: dict[str, str] = {
    "vbt-pro:signals": "signals",
    "vbt-pro:orders": "orders",
    "vbt-pro:optimizer": "optimizer",
    "vbt-pro:holding": "holding",
    "vbt-pro:random": "random",
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
        explicit_kwargs = dict(cfg.pop("kwargs", {}) or {})
        if cls_name == "FallbackBacktestEngine":
            explicit_kwargs = {**cfg, **explicit_kwargs}
        # Inject ``mode`` for the ``vbt-pro:<mode>`` shortcuts unless the
        # user already specified one explicitly.
        if key in _MODE_INJECTIONS:
            explicit_kwargs.setdefault("mode", _MODE_INJECTIONS[key])
        cfg = {"class": cls_name, "module_path": module_path, "kwargs": explicit_kwargs}
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
        "VectorbtProEngine": "vectorbt-pro",
        "VectorbtEngine": "vectorbt",
        "FallbackBacktestEngine": "fallback",
        "BacktestingPyEngine": "backtesting",
        "ZvtBacktestEngine": "zvt",
        "AatBacktestEngine": "aat",
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


def _ml_linkage_from_strategy_cfg(
    strategy_cfg: dict[str, Any], deployment_id: str | None
) -> dict[str, Any]:
    """Extract ML linkage hints (Alembic 0025) injected by AlphaBacktestExperiment.

    The orchestrator stamps a ``ml_linkage`` block on ``strategy.kwargs`` so
    the runner can populate the four new FKs on ``BacktestRun`` without
    bloating the public ``run_backtest_from_config`` signature.
    """
    out: dict[str, Any] = {}
    kwargs = strategy_cfg.get("kwargs", {}) if isinstance(strategy_cfg, dict) else {}
    linkage = kwargs.get("ml_linkage", {}) if isinstance(kwargs, dict) else {}
    if isinstance(linkage, dict):
        for key in (
            "model_version_id",
            "ml_experiment_run_id",
            "experiment_plan_id",
            "model_deployment_id",
        ):
            if linkage.get(key):
                out[key] = str(linkage[key])
    if deployment_id and "model_deployment_id" not in out:
        out["model_deployment_id"] = str(deployment_id)
    return out


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


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _bars_from_iceberg(
    identifier: str,
    *,
    symbols: list[Symbol],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    import duckdb

    conn = duckdb.connect(":memory:", read_only=False)
    try:
        view_name = iceberg_catalog.iceberg_to_duckdb_view(conn, identifier, view_name="bars_src")
        if not view_name:
            return pd.DataFrame()
        info = conn.execute(f"PRAGMA table_info({_quote_ident(view_name)})").fetchdf()
        cols = {str(c).lower(): str(c) for c in info["name"].tolist()}

        ts_col = next((cols[k] for k in ("timestamp", "ts", "datetime", "date") if k in cols), None)
        sym_col = next((cols[k] for k in ("vt_symbol", "symbol", "ticker", "instrument") if k in cols), None)
        open_col = next((cols[k] for k in ("open", "o", "open_price") if k in cols), None)
        high_col = next((cols[k] for k in ("high", "h", "high_price") if k in cols), None)
        low_col = next((cols[k] for k in ("low", "l", "low_price") if k in cols), None)
        close_col = next((cols[k] for k in ("close", "c", "adj_close", "close_price") if k in cols), None)
        volume_col = next((cols[k] for k in ("volume", "vol", "v") if k in cols), None)

        if not ts_col or not sym_col or not all((open_col, high_col, low_col, close_col)):
            return pd.DataFrame()

        vt_list = [s.vt_symbol for s in symbols]
        ticker_list = [s.ticker for s in symbols]
        sym_placeholders = ",".join(["?"] * len(vt_list)) if vt_list else ""
        ticker_placeholders = ",".join(["?"] * len(ticker_list)) if ticker_list else ""

        where = [f"{_quote_ident(ts_col)} >= ?", f"{_quote_ident(ts_col)} <= ?"]
        args: list[Any] = [start.to_pydatetime(), end.to_pydatetime()]
        if vt_list and ticker_list:
            where.append(
                f"({_quote_ident(sym_col)} IN ({sym_placeholders}) OR {_quote_ident(sym_col)} IN ({ticker_placeholders}))"
            )
            args.extend(vt_list)
            args.extend(ticker_list)
        elif vt_list:
            where.append(f"{_quote_ident(sym_col)} IN ({sym_placeholders})")
            args.extend(vt_list)

        select_cols = [
            f"{_quote_ident(ts_col)} AS timestamp",
            f"{_quote_ident(sym_col)} AS vt_symbol",
            f"{_quote_ident(open_col)} AS open",
            f"{_quote_ident(high_col)} AS high",
            f"{_quote_ident(low_col)} AS low",
            f"{_quote_ident(close_col)} AS close",
            (f"{_quote_ident(volume_col)} AS volume" if volume_col else "0.0 AS volume"),
        ]
        sql = (
            f"SELECT {', '.join(select_cols)} FROM {_quote_ident(view_name)} "
            f"WHERE {' AND '.join(where)} ORDER BY timestamp, vt_symbol"
        )
        return conn.execute(sql, args).fetchdf()
    finally:
        conn.close()


def _load_bars(
    strategy_cfg: dict[str, Any],
    cfg: dict[str, Any],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    symbols = _symbols_from_strategy_cfg(strategy_cfg)
    source = dict(cfg.get("data_source") or {})
    source_kind = str(source.get("kind") or "bars_default").lower()
    source_meta = {"kind": source_kind, **source}

    if source_kind == "parquet_root":
        config = dict(source.get("config") or {})
        parquet_root = str(
            config.get("parquet_root") or source.get("parquet_root") or ""
        ).strip()
        if not parquet_root:
            raise ValueError("data_source.kind=parquet_root requires config.parquet_root")
        hive_partitioning = bool(
            config.get("hive_partitioning") or source.get("hive_partitioning")
        )
        glob_pattern = config.get("glob_pattern") or source.get("glob_pattern")
        column_map = dict(config.get("column_map") or source.get("column_map") or {})
        provider = DuckDBHistoryProvider(
            parquet_dir=Path(parquet_root),
            hive_partitioning=hive_partitioning,
            glob_pattern=str(glob_pattern) if glob_pattern else None,
            column_map=column_map or None,
        )
        bars = provider.get_bars(symbols, start=start, end=end)
        source_meta["resolved_path"] = parquet_root
        source_meta["hive_partitioning"] = hive_partitioning
        if glob_pattern:
            source_meta["glob_pattern"] = str(glob_pattern)
        if column_map:
            source_meta["column_map"] = column_map
        return bars, source_meta

    if source_kind == "iceberg_table":
        identifier = str((source.get("config") or {}).get("iceberg_identifier") or source.get("iceberg_identifier") or "").strip()
        if not identifier:
            raise ValueError("data_source.kind=iceberg_table requires config.iceberg_identifier")
        bars = _bars_from_iceberg(identifier, symbols=symbols, start=start, end=end)
        source_meta["iceberg_identifier"] = identifier
        return bars, source_meta

    provider = DuckDBHistoryProvider()
    bars = provider.get_bars(symbols, start=start, end=end)
    return bars, source_meta


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

    bars, source_meta = _load_bars(strategy_cfg, cfg, start=start, end=end)
    symbols = _symbols_from_strategy_cfg(strategy_cfg)
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
    actual_engine = summary.get("selected_engine") or summary.get("engine") or engine_label
    summary["engine"] = actual_engine
    summary["data_source"] = source_meta
    deployment_id = _deployment_id_from_strategy_cfg(strategy_cfg)
    if deployment_id:
        summary["model_deployment_id"] = deployment_id
    dataset_hash = _dataset_hash_for_deployment(deployment_id)
    ml_linkage = _ml_linkage_from_strategy_cfg(strategy_cfg, deployment_id)
    if ml_linkage:
        summary["ml_linkage"] = ml_linkage
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
                engine=str(actual_engine),
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
            engine_label=str(actual_engine),
            dataset_hash=dataset_hash,
            strategy_id=strategy_id,
            ml_linkage=ml_linkage,
        )

    return {
        "run_id": row_id,
        "mlflow_run_id": mlflow_run_id,
        "run_name": run_name,
        "engine": actual_engine,
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
    ml_linkage: dict[str, Any] | None = None,
) -> str:
    linkage = dict(ml_linkage or {})
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
        model_version_id=linkage.get("model_version_id"),
        ml_experiment_run_id=linkage.get("ml_experiment_run_id"),
        experiment_plan_id=linkage.get("experiment_plan_id"),
        model_deployment_id=linkage.get("model_deployment_id"),
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        metrics={
            **summary,
            "equity_curve": equity_dict,
            "run_name": run_name,
            "strategy_config": strategy_cfg,
            "engine": engine_label,
            "timeline": _serialize_timeline(result),
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


_MAX_TIMELINE_ROWS = 5000


def _serialize_timeline(result) -> dict[str, Any]:
    """Serialize trades/signals/orders for later UI overlays.

    Capped at ``_MAX_TIMELINE_ROWS`` rows per stream so the JSONB blob
    stays manageable; longer histories should use the dedicated
    ``agent_decisions`` table or MLflow artifacts.
    """

    def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
        if df is None or len(df) == 0:
            return []
        out = df.tail(_MAX_TIMELINE_ROWS).copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                out[col] = out[col].astype(str)
        return out.to_dict(orient="records")

    return {
        "trades": _df_to_records(getattr(result, "trades", None)),
        "signals": _df_to_records(getattr(result, "signals", None)),
        "orders": _df_to_records(getattr(result, "orders", None)),
    }


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
