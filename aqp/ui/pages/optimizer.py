"""Optimizer Lab — parameter sweeps with a live heatmap.

Tabs:

- **Setup** — paste a base strategy YAML, declare the parameter grid,
  submit to ``POST /backtest/optimize``.
- **Runs** — list of past sweeps; click one to open its detail.
- **Results** — grid of trials + heatmap (when the sweep has exactly two
  swept parameters), plus top-N trials and the best-config block.

Two sweep methods are supported — ``grid`` (Cartesian product) and
``random`` (uniform sample). The page wires directly into the
:mod:`aqp.backtest.optimizer` + :mod:`aqp.tasks.optimize_tasks` pipeline.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara
import yaml

from aqp.ui.api_client import post
from aqp.ui.components import (
    EntityTable,
    Heatmap,
    MetricTile,
    TabPanel,
    TabSpec,
    TaskStreamer,
    YamlEditor,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader

_DEFAULT_BASE = """\
name: sweep-demo
strategy:
  class: FrameworkAlgorithm
  module_path: aqp.strategies.framework
  kwargs:
    universe_model:
      class: StaticUniverse
      module_path: aqp.strategies.universes
      kwargs:
        symbols: [SPY, AAPL, MSFT]
    alpha_model:
      class: MeanReversionAlpha
      module_path: aqp.strategies.mean_reversion
      kwargs:
        lookback: 20
        z_threshold: 2.0
    portfolio_model:
      class: EqualWeightPortfolio
      module_path: aqp.strategies.portfolio
      kwargs:
        max_positions: 3
    risk_model:
      class: BasicRiskModel
      module_path: aqp.strategies.risk_models
      kwargs:
        max_position_pct: 0.2
        max_drawdown_pct: 0.15
    execution_model:
      class: MarketOrderExecution
      module_path: aqp.strategies.execution
      kwargs: {}
    rebalance_every: 5
backtest:
  class: EventDrivenBacktester
  module_path: aqp.backtest.engine
  kwargs:
    initial_cash: 100000.0
    commission_pct: 0.0005
    slippage_bps: 2.0
    start: 2023-01-01
    end: 2024-12-31
"""

_DEFAULT_PARAMS = """\
- path: strategy.kwargs.alpha_model.kwargs.lookback
  values: [10, 20, 30, 50]
- path: strategy.kwargs.alpha_model.kwargs.z_threshold
  values: [1.5, 2.0, 2.5, 3.0]
"""


@solara.component
def Page() -> None:
    base_yaml = solara.use_reactive(_DEFAULT_BASE)
    params_yaml = solara.use_reactive(_DEFAULT_PARAMS)
    method = solara.use_reactive("grid")
    metric = solara.use_reactive("sharpe")
    n_random = solara.use_reactive("32")
    max_trials = solara.use_reactive("64")
    run_name = solara.use_reactive("sweep-demo")
    last_task_id = solara.use_reactive("")

    runs = use_api("/backtest/optimize?limit=20", default=[], interval=15.0)
    selected_id = solara.use_reactive("")
    detail = use_api(
        f"/backtest/optimize/{selected_id.value}/results" if selected_id.value else None,
        default={},
        interval=5.0 if selected_id.value else None,
    )

    def _submit() -> None:
        try:
            base = yaml.safe_load(base_yaml.value) or {}
            params = yaml.safe_load(params_yaml.value) or []
            if not isinstance(params, list):
                raise ValueError("Parameters must be a list")
            body = {
                "config": base,
                "parameters": params,
                "method": method.value,
                "metric": metric.value,
                "n_random": _to_int(n_random.value, 32),
                "max_trials": _to_int(max_trials.value, 64),
                "run_name": run_name.value or "sweep",
            }
            resp = post("/backtest/optimize", json=body)
            last_task_id.set(resp.get("task_id", ""))
            runs.refresh()
        except Exception as exc:  # noqa: BLE001
            solara.Error(str(exc))

    PageHeader(
        title="Optimizer Lab",
        subtitle=(
            "Grid or random parameter sweeps over any strategy recipe. Each "
            "trial runs through the normal backtest pipeline; results power "
            "a Sharpe heatmap."
        ),
        icon="🎯",
        actions=lambda: solara.Button("Refresh", on_click=runs.refresh, outlined=True, dense=True),
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        TabPanel(
            tabs=[
                TabSpec(
                    key="setup",
                    label="Setup",
                    render=lambda: _setup_tab(
                        base_yaml=base_yaml,
                        params_yaml=params_yaml,
                        method=method,
                        metric=metric,
                        n_random=n_random,
                        max_trials=max_trials,
                        run_name=run_name,
                        task_id=last_task_id.value,
                        on_submit=_submit,
                    ),
                ),
                TabSpec(
                    key="runs",
                    label="Runs",
                    badge=len(runs.value or []),
                    render=lambda: _runs_tab(
                        runs=runs.value or [],
                        selected_id=selected_id,
                    ),
                ),
                TabSpec(
                    key="results",
                    label="Results",
                    render=lambda: _results_tab(
                        detail=detail.value or {},
                    ),
                ),
            ]
        )


def _setup_tab(
    *,
    base_yaml,
    params_yaml,
    method,
    metric,
    n_random,
    max_trials,
    run_name,
    task_id: str,
    on_submit,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Run"):
            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                solara.InputText("run_name", value=run_name)
                solara.Select(
                    label="Method",
                    value=method,
                    values=["grid", "random"],
                )
                solara.Select(
                    label="Metric (maximise)",
                    value=metric,
                    values=["sharpe", "sortino", "total_return", "final_equity"],
                )
                solara.InputText("n_random (random only)", value=n_random)
                solara.InputText("max_trials", value=max_trials)
            solara.Button("Launch sweep", on_click=on_submit, color="primary")
        with solara.Card("Base strategy YAML"):
            YamlEditor(value=base_yaml, rows=20, show_preview=False)
        with solara.Card("Parameter space (YAML list)"):
            solara.Markdown(
                "Each entry is a dotted path plus either a ``values:`` list or "
                "``low: / high: / step:`` numeric range."
            )
            YamlEditor(value=params_yaml, rows=12, show_preview=False)
        if task_id:
            TaskStreamer(task_id=task_id, title="Sweep worker stream", show_result=True)


def _runs_tab(
    *,
    runs: list[dict[str, Any]],
    selected_id: solara.Reactive[str],
) -> None:
    if not runs:
        solara.Markdown("_No optimization runs yet._")
        return
    with solara.Column(gap="8px"):
        EntityTable(
            rows=runs,
            columns=[
                "id",
                "run_name",
                "status",
                "method",
                "metric",
                "n_trials",
                "n_completed",
                "best_metric_value",
                "created_at",
            ],
            on_row_click=lambda row: selected_id.set(row.get("id") or ""),
            id_column="id",
            label_columns=["run_name"],
            title="Recent sweeps",
        )


def _results_tab(detail: dict[str, Any]) -> None:
    if not detail:
        solara.Markdown("_Pick a sweep on the Runs tab to see its results._")
        return
    trials = detail.get("trials") or []
    _kpi_strip(detail)
    if not trials:
        solara.Markdown("_Sweep has no trials yet._")
        return
    _top_table(trials, metric=detail.get("metric") or "sharpe")
    _heatmap(detail.get("parameter_space") or [], trials, metric=detail.get("metric") or "sharpe")


def _kpi_strip(detail: dict[str, Any]) -> None:
    summary = detail.get("summary") or {}
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile("Status", (detail.get("status") or "").upper(), tone=_tone(detail.get("status")))
        MetricTile("Method", detail.get("method") or "")
        MetricTile("Metric", detail.get("metric") or "")
        MetricTile("Trials", len(detail.get("trials") or []))
        MetricTile(
            "Best value",
            summary.get("best_metric_value"),
            tone="success" if summary.get("best_metric_value") else "neutral",
        )
        MetricTile("Mean", summary.get("mean"))


def _tone(status: Any) -> str:
    s = str(status or "").lower()
    return {
        "running": "info",
        "completed": "success",
        "error": "error",
    }.get(s, "neutral")


def _top_table(trials: list[dict[str, Any]], *, metric: str) -> None:
    df = pd.DataFrame(trials)
    if df.empty:
        return
    if metric not in df.columns and "metric_value" in df.columns:
        metric_col = "metric_value"
    else:
        metric_col = metric if metric in df.columns else None
    if metric_col:
        df = df.sort_values(metric_col, ascending=False)
    df["parameters"] = df["parameters"].apply(
        lambda p: ", ".join(f"{k.split('.')[-1]}={v}" for k, v in (p or {}).items())
    )
    EntityTable(
        rows=df.head(25).to_dict(orient="records"),
        columns=[
            "trial_index",
            "status",
            "parameters",
            metric_col or "metric_value",
            "sharpe",
            "total_return",
            "max_drawdown",
        ],
        title="Top trials",
    )


def _heatmap(
    parameter_space: list[dict[str, Any]],
    trials: list[dict[str, Any]],
    *,
    metric: str,
) -> None:
    numeric_params = [p for p in parameter_space if _is_numeric_space(p)]
    if len(numeric_params) < 2:
        return
    x_path = numeric_params[0]["path"]
    y_path = numeric_params[1]["path"]
    rows = [
        t
        for t in trials
        if isinstance(t.get("parameters"), dict)
        and x_path in t["parameters"]
        and y_path in t["parameters"]
    ]
    if not rows:
        return
    df = pd.DataFrame(
        [
            {
                "x": t["parameters"][x_path],
                "y": t["parameters"][y_path],
                "metric": t.get("metric_value") or t.get(metric),
            }
            for t in rows
            if t.get("metric_value") is not None or t.get(metric) is not None
        ]
    )
    if df.empty:
        return
    pivot = df.pivot_table(index="y", columns="x", values="metric", aggfunc="mean")
    Heatmap(
        pivot.sort_index().sort_index(axis=1),
        title=f"{metric} across ({_short(x_path)}, {_short(y_path)})",
        xaxis_title=_short(x_path),
        yaxis_title=_short(y_path),
        zmid=None,
        show_values=True,
        value_fmt=".2f",
    )


def _is_numeric_space(spec: dict[str, Any]) -> bool:
    values = spec.get("values")
    if values is not None:
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
    return all(spec.get(k) is not None for k in ("low", "high", "step"))


def _short(path: str) -> str:
    return path.split(".")[-1]


def _to_int(text: str, default: int) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default
