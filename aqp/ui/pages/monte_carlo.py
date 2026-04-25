"""Monte Carlo Lab — resample the returns of an existing backtest.

Wraps the existing ``POST /backtest/monte_carlo`` endpoint. Takes a
backtest id, a run count, and a method (bootstrap / parametric), then
shows the percentile summary and a spaghetti plot of the synthetic
equity paths.

The backend already produces percentile summaries for Sharpe / Sortino /
MaxDD / TotalReturn; the UI adds a spaghetti visualisation by locally
regenerating a few paths from the fetched equity curve.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import solara

from aqp.ui.api_client import get, post
from aqp.ui.components import (
    EntityTable,
    MetricTile,
    StatsGrid,
    TaskStreamer,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader


@solara.component
def Page() -> None:
    runs = use_api("/backtest/runs?limit=30", default=[])
    backtest_id = solara.use_reactive("")
    n_runs = solara.use_reactive("500")
    method = solara.use_reactive("bootstrap")
    n_preview_paths = solara.use_reactive("50")
    last_task_id = solara.use_reactive("")
    last_summary: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    equity_plot: solara.Reactive[dict[str, Any] | None] = solara.use_reactive(None)

    def _submit() -> None:
        if not backtest_id.value.strip():
            solara.Warning("Pick a backtest run first.")
            return
        try:
            resp = post(
                "/backtest/monte_carlo",
                json={
                    "backtest_id": backtest_id.value.strip(),
                    "n_runs": _to_int(n_runs.value, 500),
                    "method": method.value,
                },
            )
            last_task_id.set(resp.get("task_id", ""))
            last_summary.set({})
            equity_plot.set(None)
        except Exception as exc:  # noqa: BLE001
            solara.Error(str(exc))

    def _pick_run(row: dict[str, Any]) -> None:
        rid = row.get("id") or ""
        backtest_id.set(rid)
        try:
            equity_plot.set(get(f"/backtest/runs/{rid}/plot/equity"))
        except Exception:
            equity_plot.set(None)

    PageHeader(
        title="Monte Carlo Lab",
        subtitle=(
            "Resample trade returns of a completed backtest to stress-test "
            "its robustness. Pick a run on the left, pick a method, and "
            "submit."
        ),
        icon="🎲",
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        with solara.Card("Pick a backtest"):
            EntityTable(
                rows=runs.value or [],
                columns=["id", "status", "sharpe", "total_return", "max_drawdown", "created_at"],
                on_row_click=_pick_run,
                id_column="id",
                label_columns=["sharpe"],
                title="Recent runs",
                empty="_No backtests yet._",
            )

        with solara.Card("Monte Carlo configuration"):
            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                solara.InputText("backtest_id", value=backtest_id)
                solara.InputText("n_runs", value=n_runs)
                solara.Select(
                    label="Method",
                    value=method,
                    values=["bootstrap", "parametric"],
                )
                solara.InputText("# preview paths", value=n_preview_paths)
            solara.Button("Run Monte Carlo", on_click=_submit, color="primary")

        if last_task_id.value:
            TaskStreamer(
                task_id=last_task_id.value,
                title="MC worker stream",
                show_result=True,
            )

        if equity_plot.value and "data" in equity_plot.value:
            _spaghetti(
                backtest_equity=equity_plot.value,
                n_paths=_to_int(n_preview_paths.value, 50),
                method=method.value,
            )


def _spaghetti(
    *,
    backtest_equity: dict[str, Any],
    n_paths: int,
    method: str,
) -> None:
    """Generate + render a spaghetti plot locally for visual intuition.

    The official statistics still come from the backend ``run_monte_carlo``
    task (streamed into the TaskStreamer above). This local plot is a
    quick preview so users can see what ``bootstrap`` vs ``parametric``
    actually looks like without waiting for the full sweep.
    """
    try:
        import plotly.graph_objects as go

        # Reconstruct the equity series from the stored Plotly payload.
        series = _extract_equity_series(backtest_equity)
        if series is None or len(series) < 10:
            return
        returns = series.pct_change().dropna()
        if returns.empty:
            return
        rng = np.random.default_rng(42)
        initial = float(series.iloc[0])
        mean = float(returns.mean())
        std = float(returns.std(ddof=0) or 0.0)
        paths = []
        n_paths = max(1, min(n_paths, 200))
        for _ in range(n_paths):
            if method == "parametric" and std:
                sampled = rng.normal(mean, std, size=len(returns))
            else:
                sampled = rng.choice(returns.values, size=len(returns), replace=True)
            eq = initial * (1 + pd.Series(sampled)).cumprod()
            paths.append(eq.values)

        percentiles = np.percentile(paths, [5, 50, 95], axis=0)

        fig = go.Figure()
        for eq in paths:
            fig.add_trace(
                go.Scatter(
                    y=eq,
                    mode="lines",
                    line={"width": 0.6, "color": "rgba(59,130,246,0.2)"},
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        for name, row, color in zip(
            ("p05", "p50", "p95"),
            percentiles,
            ("#f59e0b", "#22c55e", "#3b82f6"),
            strict=True,
        ):
            fig.add_trace(
                go.Scatter(
                    y=row,
                    mode="lines",
                    name=name,
                    line={"width": 2.0, "color": color},
                )
            )
        fig.update_layout(
            title=f"Monte Carlo preview ({method}, {n_paths} paths)",
            xaxis_title="bar",
            yaxis_title="equity",
            height=420,
            margin={"l": 60, "r": 20, "t": 40, "b": 30},
        )
        with solara.Card("Preview paths"):
            solara.FigurePlotly(fig)
            StatsGrid(
                {
                    "p05 (final)": float(percentiles[0][-1]),
                    "p50 (final)": float(percentiles[1][-1]),
                    "p95 (final)": float(percentiles[2][-1]),
                    "mean return (bar)": mean,
                    "std (bar)": std,
                },
                columns=5,
            )
    except Exception as exc:  # noqa: BLE001
        solara.Markdown(f"_Preview error: {exc}_")


def _extract_equity_series(fig_json: dict[str, Any]) -> pd.Series | None:
    """Pull the y-values of the first scatter trace as a Series."""
    try:
        traces = fig_json.get("data") or []
        if not traces:
            return None
        first = traces[0]
        y = first.get("y") or []
        x = first.get("x") or list(range(len(y)))
        if not y:
            return None
        return pd.Series(y, index=x)
    except Exception:
        return None


def _to_int(text: str, default: int) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default
