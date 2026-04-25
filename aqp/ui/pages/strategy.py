"""Strategy Workbench — build, save, test, diff, and review strategies.

This page is the main authoring surface for a recipe strategy:

- **Build** — pick data inputs, alpha / portfolio / risk / execution models
  via a :class:`ParameterEditor`-driven form, and an engine.
- **YAML** — edit the generated recipe by hand with live validation and a
  diff against the currently loaded saved strategy.
- **Test** — pick an engine + optional window and dispatch a backtest
  against the latest saved version. Streams progress via
  :class:`TaskStreamer`.
- **Versions** — list every immutable version snapshot and diff any two.
- **Results** — browse the backtest runs linked to this strategy with the
  equity curve, drawdown, and KPIs.

Compared to the old 710-line ``strategy.py``, this refactor leans on the
shared component library (:mod:`aqp.ui.components`) so the body is ~300
lines and the parts are swappable.
"""
from __future__ import annotations

import contextlib
import difflib
import json
from datetime import datetime
from typing import Any

import pandas as pd
import solara
import yaml

from aqp.ui.api_client import get, post, put
from aqp.ui.components import (
    EntityTable,
    EquityCard,
    MetricTile,
    ModelCatalog,
    ParameterEditor,
    TabPanel,
    TabSpec,
    TaskStreamer,
    YamlEditor,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader


# ---------------------------------------------------------------------------
# Static catalogs — adding an entry here surfaces a new component in the UI.
# ---------------------------------------------------------------------------


ALPHA_CATALOG = ModelCatalog(
    label="Alpha model",
    help="Generates insights / signals from bar data.",
    entries={
        "MeanReversionAlpha": {
            "module_path": "aqp.strategies.mean_reversion",
            "kwargs": {"lookback": 20, "z_threshold": 2.0, "hold_bars": 5},
        },
        "MomentumAlpha": {
            "module_path": "aqp.strategies.momentum",
            "kwargs": {
                "lookback": 90,
                "top_quantile": 0.3,
                "bottom_quantile": 0.3,
                "allow_short": False,
            },
        },
        "EmaCrossAlphaModel": {
            "module_path": "aqp.strategies.ema_cross_alpha",
            "kwargs": {"fast": 12, "slow": 26},
        },
        "MacdAlphaModel": {
            "module_path": "aqp.strategies.macd_alpha",
            "kwargs": {"fast": 12, "slow": 26, "signal": 9},
        },
        "RsiAlphaModel": {
            "module_path": "aqp.strategies.rsi_alpha",
            "kwargs": {"period": 14, "overbought": 70.0, "oversold": 30.0},
        },
        "BollingerWAlpha": {
            "module_path": "aqp.strategies.bollinger_w_alpha",
            "kwargs": {"period": 20, "std_dev": 2.0},
        },
        "DeployedModelAlpha": {
            "module_path": "aqp.strategies.ml_alphas",
            "kwargs": {
                "deployment_id": "",
                "infer_segment": "infer",
                "long_threshold": 0.001,
                "short_threshold": -0.001,
                "allow_short": True,
                "top_k": 25,
            },
        },
    },
)

PORTFOLIO_CATALOG = ModelCatalog(
    label="Portfolio",
    help="Allocates capital across the chosen insights.",
    entries={
        "EqualWeightPortfolio": {
            "module_path": "aqp.strategies.portfolio",
            "kwargs": {"max_positions": 5, "long_only": True},
        },
        "SignalWeightedPortfolio": {
            "module_path": "aqp.strategies.portfolio",
            "kwargs": {"max_positions": 10, "long_only": True},
        },
        "MeanVariancePortfolio": {
            "module_path": "aqp.strategies.mean_variance",
            "kwargs": {"lookback": 90, "risk_aversion": 1.0},
        },
        "RiskParityPortfolio": {
            "module_path": "aqp.strategies.risk_parity",
            "kwargs": {"lookback": 90},
        },
        "HierarchicalRiskParity": {
            "module_path": "aqp.strategies.hrp",
            "kwargs": {"lookback": 90},
        },
        "BlackLittermanPortfolio": {
            "module_path": "aqp.strategies.black_litterman",
            "kwargs": {"lookback": 90, "tau": 0.05},
        },
    },
)

RISK_CATALOG = ModelCatalog(
    label="Risk model",
    help="Pre-trade checks and capital limits.",
    entries={
        "BasicRiskModel": {
            "module_path": "aqp.strategies.risk_models",
            "kwargs": {"max_position_pct": 0.2, "max_drawdown_pct": 0.15, "leverage": 1.0},
        },
        "NoOpRiskModel": {
            "module_path": "aqp.strategies.risk_models",
            "kwargs": {},
        },
        "TrailingStopRisk": {
            "module_path": "aqp.strategies.trailing_stop",
            "kwargs": {"trailing_pct": 0.05},
        },
    },
)

EXECUTION_CATALOG = ModelCatalog(
    label="Execution",
    help="How orders reach the venue.",
    entries={
        "MarketOrderExecution": {
            "module_path": "aqp.strategies.execution",
            "kwargs": {},
        },
        "TwapExecution": {
            "module_path": "aqp.strategies.twap_execution",
            "kwargs": {"slices": 5, "interval_seconds": 60},
        },
        "VwapExecution": {
            "module_path": "aqp.strategies.vwap_execution",
            "kwargs": {"slices": 5, "interval_seconds": 60},
        },
    },
)

ENGINES: dict[str, dict[str, Any]] = {
    "EventDrivenBacktester": {
        "module_path": "aqp.backtest.engine",
        "kwargs": {"initial_cash": 100000.0, "commission_pct": 0.0005, "slippage_bps": 2.0},
        "submit": "/backtest/run",
        "description": "Chronological bar replay with slippage + commissions.",
    },
    "VectorizedBacktester": {
        "module_path": "aqp.backtest.vectorized",
        "kwargs": {"initial_cash": 100000.0, "commission_pct": 0.0005},
        "submit": "/backtest/run",
        "description": "Pandas-vectorized, rapid screening. Signals lagged one bar.",
    },
    "WalkForwardOptimization": {
        "module_path": "aqp.backtest.walk_forward",
        "kwargs": {"initial_cash": 100000.0, "commission_pct": 0.0005, "slippage_bps": 2.0},
        "submit": "/backtest/walk_forward",
        "description": "Rolling in-sample / out-of-sample windows for overfitting control.",
    },
    "DryRunPaper": {
        "module_path": None,
        "kwargs": {"initial_cash": 100000.0, "max_bars": 500},
        "submit": "/paper/start",
        "description": "Replays the parquet lake through the paper engine — same code path as live.",
    },
}

DATA_SOURCES = {
    "parquet-lake": "Local Parquet lake (default AQP lake)",
    "local-csv": "LocalCSVSource — CSV files on a mounted drive",
    "local-parquet": "LocalParquetSource — Parquet files on a mounted drive",
}


# ---------------------------------------------------------------------------
# Config assembly
# ---------------------------------------------------------------------------


def _build_config(
    *,
    run_name: str,
    symbols: list[str],
    start: str,
    end: str,
    initial_cash: float,
    commission: float,
    slippage: float,
    rebalance_every: int,
    alpha_block: dict[str, Any],
    portfolio_block: dict[str, Any],
    risk_block: dict[str, Any],
    execution_block: dict[str, Any],
    engine: str,
    data_source: str,
    data_root: str,
    data_glob: str,
    data_tz: str,
) -> dict[str, Any]:
    strategy_block = {
        "class": "FrameworkAlgorithm",
        "module_path": "aqp.strategies.framework",
        "kwargs": {
            "universe_model": {
                "class": "StaticUniverse",
                "module_path": "aqp.strategies.universes",
                "kwargs": {"symbols": symbols},
            },
            "alpha_model": alpha_block,
            "portfolio_model": portfolio_block,
            "risk_model": risk_block,
            "execution_model": execution_block,
            "rebalance_every": int(rebalance_every),
        },
    }

    engine_spec = ENGINES[engine]
    engine_kwargs = dict(engine_spec["kwargs"])
    engine_kwargs["initial_cash"] = float(initial_cash)
    if engine == "EventDrivenBacktester":
        engine_kwargs["start"] = start
        engine_kwargs["end"] = end
        engine_kwargs["commission_pct"] = float(commission)
        engine_kwargs["slippage_bps"] = float(slippage)

    cfg: dict[str, Any] = {"name": run_name, "strategy": strategy_block}
    if engine == "DryRunPaper":
        cfg["session"] = {
            "run_name": run_name,
            "initial_cash": engine_kwargs["initial_cash"],
            "max_bars": engine_kwargs.get("max_bars", 500),
            "dry_run": True,
            "stop_on_kill_switch": True,
        }
    else:
        cfg["backtest"] = {
            "class": (
                engine
                if engine in {"EventDrivenBacktester", "WalkForwardOptimization"}
                else "EventDrivenBacktester"
            ),
            "module_path": engine_spec["module_path"] or "aqp.backtest.engine",
            "kwargs": engine_kwargs,
        }

    if data_source != "parquet-lake":
        cfg["data"] = {
            "source": data_source,
            "root": data_root,
            "format": "csv" if data_source == "local-csv" else "parquet",
            "glob": data_glob or None,
            "tz": data_tz or None,
        }
    return cfg


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


@solara.component
def Page() -> None:
    # ---- Build tab state -------------------------------------------------
    run_name = solara.use_reactive("my-strategy")
    symbols = solara.use_reactive("SPY,AAPL,MSFT,GOOGL,AMZN")
    start = solara.use_reactive("2023-01-01")
    end = solara.use_reactive("2024-12-31")
    initial_cash = solara.use_reactive("100000")
    commission = solara.use_reactive("0.0005")
    slippage = solara.use_reactive("2.0")
    rebalance_every = solara.use_reactive("5")
    engine = solara.use_reactive("EventDrivenBacktester")
    data_source = solara.use_reactive("parquet-lake")
    data_root = solara.use_reactive("")
    data_glob = solara.use_reactive("")
    data_tz = solara.use_reactive("")

    strategy_notes = solara.use_reactive("")
    deployment_profile_id = solara.use_reactive("")

    # ---- Persistence + selection ---------------------------------------
    saved = use_api("/strategies/", default=[], interval=None)
    deployments = use_api("/ml/deployments?limit=100", default=[], interval=None)
    selected_id = solara.use_reactive("")
    detail = use_api(
        f"/strategies/{selected_id.value}" if selected_id.value else None,
        default={},
    )

    # ---- Test state ----------------------------------------------------
    test_engine = solara.use_reactive("EventDrivenBacktester")
    test_start = solara.use_reactive("")
    test_end = solara.use_reactive("")
    last_task_id = solara.use_reactive("")
    test_message = solara.use_reactive("")

    # ---- Version diff state --------------------------------------------
    diff_v1 = solara.use_reactive("1")
    diff_v2 = solara.use_reactive("2")
    diff_text = solara.use_reactive("")

    # ---- YAML editor buffer --------------------------------------------
    yaml_buffer = solara.use_reactive("")
    yaml_pristine = solara.use_reactive("")

    alpha = ParameterEditor(ALPHA_CATALOG)
    portfolio = ParameterEditor(PORTFOLIO_CATALOG)
    risk = ParameterEditor(RISK_CATALOG)
    execution = ParameterEditor(EXECUTION_CATALOG)

    def _deployment_rows() -> list[dict[str, Any]]:
        raw = deployments.value
        return raw if isinstance(raw, list) else []

    def _selected_deployment() -> dict[str, Any] | None:
        if not deployment_profile_id.value:
            return None
        for row in _deployment_rows():
            if row.get("id") == deployment_profile_id.value:
                return row
        return None

    def _current_config() -> dict[str, Any]:
        sym_list = [s.strip() for s in symbols.value.split(",") if s.strip()]
        alpha_block = alpha.as_block()
        selected_deployment = _selected_deployment()
        if selected_deployment:
            alpha_block = {
                "class": selected_deployment.get("alpha_class") or "DeployedModelAlpha",
                "module_path": "aqp.strategies.ml_alphas",
                "kwargs": {
                    "deployment_id": selected_deployment.get("id"),
                    "infer_segment": selected_deployment.get("infer_segment") or "infer",
                    "long_threshold": selected_deployment.get("long_threshold", 0.001),
                    "short_threshold": selected_deployment.get("short_threshold", -0.001),
                    "allow_short": selected_deployment.get("allow_short", True),
                    "top_k": selected_deployment.get("top_k"),
                    **(selected_deployment.get("deployment_config") or {}),
                },
            }
        return _build_config(
            run_name=run_name.value,
            symbols=sym_list,
            start=start.value,
            end=end.value,
            initial_cash=_to_float(initial_cash.value, 100000.0),
            commission=_to_float(commission.value, 0.0005),
            slippage=_to_float(slippage.value, 2.0),
            rebalance_every=_to_int(rebalance_every.value, 1),
            alpha_block=alpha_block,
            portfolio_block=portfolio.as_block(),
            risk_block=risk.as_block(),
            execution_block=execution.as_block(),
            engine=engine.value,
            data_source=data_source.value,
            data_root=data_root.value,
            data_glob=data_glob.value,
            data_tz=data_tz.value,
        )

    def _sync_yaml() -> None:
        """Regenerate the YAML buffer from the current Build form."""
        try:
            yaml_buffer.set(yaml.safe_dump(_current_config(), sort_keys=False))
        except Exception as exc:  # noqa: BLE001
            yaml_buffer.set(f"# ERROR: {exc}")

    def _load_selected(row: dict[str, Any]) -> None:
        sid = row.get("id") or ""
        if not sid:
            return
        selected_id.set(sid)

    def _apply_detail_yaml() -> None:
        cfg_yaml = (detail.value or {}).get("config_yaml") or ""
        if cfg_yaml:
            yaml_buffer.set(cfg_yaml)
            yaml_pristine.set(cfg_yaml)

    solara.use_effect(_apply_detail_yaml, [detail.value])

    def _save_new() -> None:
        try:
            body = {
                "name": run_name.value or "strategy",
                "config_yaml": yaml_buffer.value or yaml.safe_dump(_current_config(), sort_keys=False),
                "author": "ui",
                "notes": strategy_notes.value,
            }
            resp = post("/strategies/", json=body)
            solara.Info(f"Saved v{resp.get('version')} of {resp.get('name')}")
            selected_id.set(resp.get("id", ""))
            saved.refresh()
        except Exception as exc:  # noqa: BLE001
            solara.Error(str(exc))

    def _save_new_version() -> None:
        if not selected_id.value:
            solara.Warning("Pick a saved strategy first.")
            return
        try:
            body = {
                "config_yaml": yaml_buffer.value
                or yaml.safe_dump(_current_config(), sort_keys=False),
                "author": "ui",
                "notes": strategy_notes.value,
            }
            resp = put(f"/strategies/{selected_id.value}", json=body)
            solara.Info(f"Saved v{resp.get('version')}")
            detail.refresh()
        except Exception as exc:  # noqa: BLE001
            solara.Error(str(exc))

    def _run_test() -> None:
        if not selected_id.value:
            solara.Warning("Save the strategy first.")
            return
        try:
            body: dict[str, Any] = {"engine": test_engine.value}
            if test_start.value.strip():
                body["start"] = test_start.value
            if test_end.value.strip():
                body["end"] = test_end.value
            resp = post(f"/strategies/{selected_id.value}/test", json=body)
            last_task_id.set(resp.get("task_id", ""))
            test_message.set(f"Queued: {resp.get('task_id')}")
            detail.refresh()
        except Exception as exc:  # noqa: BLE001
            test_message.set(f"error: {exc}")

    def _show_diff() -> None:
        if not selected_id.value:
            return
        try:
            target = int(diff_v2.value)
            against = int(diff_v1.value)
            resp = get(
                f"/strategies/{selected_id.value}/versions/{target}/diff?against={against}"
            )
            diff_text.set(resp.get("diff") or "(no differences)")
        except Exception as exc:  # noqa: BLE001
            diff_text.set(f"ERROR: {exc}")

    PageHeader(
        title="Strategy Workbench",
        subtitle=(
            "Compose a five-stage recipe (universe → alpha → portfolio → risk → "
            "execution), preview the YAML, save + version, and dispatch tests."
        ),
        icon="🛠️",
        actions=lambda: _header_actions(saved, selected_id, saved.refresh),
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        _selected_summary(detail.value or {})
        TabPanel(
            tabs=[
                TabSpec(
                    key="build",
                    label="Build",
                    render=lambda: _build_tab(
                        run_name=run_name,
                        symbols=symbols,
                        start=start,
                        end=end,
                        initial_cash=initial_cash,
                        commission=commission,
                        slippage=slippage,
                        rebalance_every=rebalance_every,
                        engine=engine,
                        data_source=data_source,
                        data_root=data_root,
                        data_glob=data_glob,
                        data_tz=data_tz,
                        deployment_profile_id=deployment_profile_id,
                        deployments=_deployment_rows(),
                        sync_yaml=_sync_yaml,
                    ),
                ),
                TabSpec(
                    key="yaml",
                    label="YAML",
                    render=lambda: _yaml_tab(
                        yaml_buffer=yaml_buffer,
                        pristine=yaml_pristine.value,
                        notes=strategy_notes,
                        on_save_new=_save_new,
                        on_save_version=_save_new_version,
                        sync_yaml=_sync_yaml,
                    ),
                ),
                TabSpec(
                    key="test",
                    label="Test",
                    render=lambda: _test_tab(
                        selected_id=selected_id.value,
                        test_engine=test_engine,
                        test_start=test_start,
                        test_end=test_end,
                        last_task_id=last_task_id.value,
                        message=test_message.value,
                        on_run=_run_test,
                        recent_tests=(detail.value or {}).get("tests") or [],
                    ),
                ),
                TabSpec(
                    key="versions",
                    label="Versions",
                    render=lambda: _versions_tab(
                        versions=(detail.value or {}).get("versions") or [],
                        diff_v1=diff_v1,
                        diff_v2=diff_v2,
                        diff_text=diff_text.value,
                        on_diff=_show_diff,
                    ),
                ),
                TabSpec(
                    key="results",
                    label="Results",
                    render=lambda: _results_tab(
                        strategy_id=selected_id.value,
                        tests=(detail.value or {}).get("tests") or [],
                    ),
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Selected-strategy summary strip
# ---------------------------------------------------------------------------


def _selected_summary(detail: dict[str, Any]) -> None:
    if not detail:
        solara.Markdown("_No saved strategy loaded — compose in Build + Save to create one._")
        return
    name = detail.get("name") or "—"
    version = detail.get("version") or 1
    status = (detail.get("status") or "draft").title()
    last = detail.get("last_sharpe")
    with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
        MetricTile("Strategy", name)
        MetricTile("Version", f"v{version}")
        MetricTile("Status", status, tone=_status_tone(detail.get("status")))
        MetricTile("Last Sharpe", last)
        MetricTile("Tests", len((detail.get("tests") or [])))


# ---------------------------------------------------------------------------
# Build tab
# ---------------------------------------------------------------------------


def _build_tab(
    *,
    run_name: solara.Reactive[str],
    symbols: solara.Reactive[str],
    start: solara.Reactive[str],
    end: solara.Reactive[str],
    initial_cash: solara.Reactive[str],
    commission: solara.Reactive[str],
    slippage: solara.Reactive[str],
    rebalance_every: solara.Reactive[str],
    engine: solara.Reactive[str],
    data_source: solara.Reactive[str],
    data_root: solara.Reactive[str],
    data_glob: solara.Reactive[str],
    data_tz: solara.Reactive[str],
    deployment_profile_id: solara.Reactive[str],
    deployments: list[dict[str, Any]],
    sync_yaml,
) -> None:
    engine_description = ENGINES[engine.value]["description"]
    with solara.Column(gap="16px"):
        with solara.Card("Run basics"):
            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                solara.InputText("run_name", value=run_name)
                solara.InputText("initial_cash (USD)", value=initial_cash)
                solara.InputText("rebalance_every (bars)", value=rebalance_every)
        with solara.Card("Data inputs"):
            solara.Select(
                label="Data source",
                value=data_source,
                values=list(DATA_SOURCES.keys()),
            )
            solara.Markdown(f"_{DATA_SOURCES[data_source.value]}_")
            solara.InputText("Universe symbols (comma-separated)", value=symbols)
            with solara.Row(gap="10px"):
                solara.InputText("start (YYYY-MM-DD)", value=start)
                solara.InputText("end (YYYY-MM-DD)", value=end)
            if data_source.value != "parquet-lake":
                solara.Markdown("_Additional path inputs for a local drive source:_")
                solara.InputText("Local root directory (absolute path)", value=data_root)
                with solara.Row(gap="10px"):
                    solara.InputText("Glob pattern (e.g. *.csv)", value=data_glob)
                    solara.InputText("Timezone (e.g. US/Eastern)", value=data_tz)
        with solara.Card("Model deployment (optional)"):
            options = [""] + [str(row.get("id")) for row in deployments if row.get("id")]
            solara.Select(
                label="Deployment profile id",
                value=deployment_profile_id,
                values=options or [""],
            )
            selected = next(
                (row for row in deployments if row.get("id") == deployment_profile_id.value),
                None,
            )
            if selected:
                solara.Markdown(
                    f"Using **{selected.get('name', 'deployment')}** "
                    f"(`{selected.get('status', 'staging')}`) as the alpha source."
                )
            else:
                solara.Markdown(
                    "_Leave blank to use the Alpha model selected in the parameter editor._"
                )
        with solara.Card("Engine"):
            with solara.Row(gap="10px"):
                solara.Select(label="Engine", value=engine, values=list(ENGINES.keys()))
            solara.Markdown(f"_{engine_description}_")
            if engine.value == "EventDrivenBacktester":
                with solara.Row(gap="10px"):
                    solara.InputText("commission_pct", value=commission)
                    solara.InputText("slippage_bps", value=slippage)
        solara.Button(
            "Preview YAML",
            on_click=sync_yaml,
            color="primary",
            outlined=True,
        )


# ---------------------------------------------------------------------------
# YAML tab
# ---------------------------------------------------------------------------


def _yaml_tab(
    *,
    yaml_buffer: solara.Reactive[str],
    pristine: str,
    notes: solara.Reactive[str],
    on_save_new,
    on_save_version,
    sync_yaml,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Row(gap="6px"):
            solara.Button("Regenerate from Build form", on_click=sync_yaml, outlined=True)
            solara.Button("Save as new strategy", on_click=on_save_new, color="primary")
            solara.Button("Save as new version", on_click=on_save_version)
        solara.InputText("Notes (optional)", value=notes)
        YamlEditor(
            value=yaml_buffer,
            rows=22,
            diff_against=pristine or None,
            on_save=lambda _: on_save_version(),
            show_preview=False,
        )


# ---------------------------------------------------------------------------
# Test tab
# ---------------------------------------------------------------------------


def _test_tab(
    *,
    selected_id: str,
    test_engine: solara.Reactive[str],
    test_start: solara.Reactive[str],
    test_end: solara.Reactive[str],
    last_task_id: str,
    message: str,
    on_run,
    recent_tests: list[dict[str, Any]],
) -> None:
    if not selected_id:
        solara.Markdown("_Save the strategy first to enable testing._")
        return
    with solara.Column(gap="12px"):
        with solara.Card("Run a test"):
            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                solara.Select(
                    label="Engine",
                    value=test_engine,
                    values=list(ENGINES.keys()),
                )
                solara.InputText("start (YYYY-MM-DD)", value=test_start)
                solara.InputText("end (YYYY-MM-DD)", value=test_end)
            solara.Button("Run test", on_click=on_run, color="warning")
            if message:
                solara.Markdown(f"`{message}`")
        if last_task_id:
            TaskStreamer(task_id=last_task_id, title="Worker stream")
        EntityTable(
            rows=recent_tests,
            columns=[
                "id",
                "status",
                "engine",
                "sharpe",
                "total_return",
                "max_drawdown",
                "created_at",
            ],
            title="Recent tests",
            empty="_No tests yet._",
        )


# ---------------------------------------------------------------------------
# Versions tab
# ---------------------------------------------------------------------------


def _versions_tab(
    *,
    versions: list[dict[str, Any]],
    diff_v1: solara.Reactive[str],
    diff_v2: solara.Reactive[str],
    diff_text: str,
    on_diff,
) -> None:
    with solara.Column(gap="12px"):
        EntityTable(rows=versions, title="Immutable snapshots", empty="_No versions yet._")
        with solara.Row(gap="10px"):
            solara.InputText("From version", value=diff_v1)
            solara.InputText("To version", value=diff_v2)
            solara.Button("Show diff", on_click=on_diff)
        if diff_text:
            solara.Markdown(f"```diff\n{diff_text}\n```")


# ---------------------------------------------------------------------------
# Results tab — equity curves for the tests linked to this strategy.
# ---------------------------------------------------------------------------


def _results_tab(*, strategy_id: str, tests: list[dict[str, Any]]) -> None:
    if not strategy_id:
        solara.Markdown("_Save and test the strategy to populate results._")
        return
    finished = [
        t for t in tests if t.get("backtest_id") and t.get("status") in {"completed", "done"}
    ]
    if not finished:
        solara.Markdown("_No completed test results yet._")
        return
    with solara.Column(gap="12px"):
        for t in finished[:5]:
            EquityCard(backtest_id=t.get("backtest_id"))


# ---------------------------------------------------------------------------
# Header actions: saved-strategy dropdown + refresh.
# ---------------------------------------------------------------------------


def _header_actions(saved, selected_id, refresh) -> None:
    values = saved.value or []
    labels = [
        f"{s.get('name')} (v{s.get('version')}) [{s.get('id', '')[:8]}]"
        for s in values
    ]
    label_to_id = {lab: s.get("id") for lab, s in zip(labels, values, strict=True)}
    current_label = next(
        (lab for lab, sid in label_to_id.items() if sid == selected_id.value),
        "",
    )
    selection = solara.use_reactive(current_label)

    def _on_pick(label: str) -> None:
        selection.set(label)
        selected_id.set(label_to_id.get(label, ""))

    solara.Select(
        label="Saved strategies",
        value=selection,
        values=labels or [""],
        on_value=_on_pick,
    )
    solara.Button("Refresh", on_click=refresh, outlined=True, dense=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_int(text: str, default: int) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _to_float(text: str, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _status_tone(status: str | None) -> str:
    if not status:
        return "neutral"
    s = status.lower()
    if s in {"live", "paper"}:
        return "success"
    if s == "retired" or s == "archived":
        return "warning"
    return "info"
