"""EquityCard — compose run summary + equity + drawdown + metrics in one panel.

Used by the refactored Backtest Lab, Strategy Workbench (Results tab), and
Strategy Browser detail pane, each of which previously repeated the exact
same Plotly + DataFrame + metric list code.
"""
from __future__ import annotations

import contextlib
from typing import Any

import solara

from aqp.ui.api_client import get


@solara.component
def EquityCard(
    backtest_id: str | None,
    *,
    show_drawdown: bool = True,
    show_metrics: bool = True,
    height: int = 420,
) -> None:
    summary: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    equity: solara.Reactive[dict[str, Any] | None] = solara.use_reactive(None)
    drawdown: solara.Reactive[dict[str, Any] | None] = solara.use_reactive(None)
    error = solara.use_reactive("")

    def _fetch() -> None:
        if not backtest_id:
            summary.set({})
            equity.set(None)
            drawdown.set(None)
            return
        error.set("")
        try:
            summary.set(get(f"/backtest/runs/{backtest_id}") or {})
        except Exception as exc:  # noqa: BLE001
            error.set(f"summary: {exc}")
        try:
            equity.set(get(f"/backtest/runs/{backtest_id}/plot/equity"))
        except Exception as exc:  # noqa: BLE001
            error.set(f"equity: {exc}")
        if show_drawdown:
            try:
                drawdown.set(get(f"/backtest/runs/{backtest_id}/plot/drawdown"))
            except Exception:
                drawdown.set(None)

    solara.use_effect(_fetch, [backtest_id])

    title = f"Run {backtest_id[:8]}" if backtest_id else "Run —"
    with solara.Card(title):
        if not backtest_id:
            solara.Markdown("_No run selected._")
            return

        if error.value:
            solara.Error(error.value)

        if show_metrics and summary.value:
            _metrics_row(summary.value)

        if equity.value:
            _render_plot(equity.value, height=height)
        else:
            solara.Markdown("_No equity curve available._")

        if show_drawdown and drawdown.value:
            _render_plot(drawdown.value, height=int(height * 0.6))


def _metrics_row(data: dict[str, Any]) -> None:
    from aqp.ui.components.data.metric_tile import MetricTile, TileTrend

    sharpe = data.get("sharpe")
    total = data.get("total_return")
    mdd = data.get("max_drawdown")
    final = data.get("final_equity")
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile("Sharpe", sharpe, tone=_tone(sharpe, good=1.0, bad=0.0))
        MetricTile("Total Return", total, unit="%", tone=_tone(total, good=0.1, bad=-0.05))
        MetricTile(
            "Max Drawdown",
            mdd,
            unit="%",
            tone=_tone(mdd, good=-0.05, bad=-0.20, reverse=True),
        )
        MetricTile("Final Equity", final, unit="$")
        if data.get("status"):
            MetricTile("Status", str(data["status"]).title())
        if sharpe is not None:
            MetricTile(
                "Sortino",
                data.get("sortino"),
                trend=TileTrend(
                    delta=float(data.get("sortino") or 0) - float(sharpe or 0),
                    label="vs Sharpe",
                ),
            )


def _tone(value: Any, *, good: float, bad: float, reverse: bool = False) -> str:
    if value is None:
        return "neutral"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if reverse:
        if v >= good:
            return "success"
        if v <= bad:
            return "error"
        return "warning"
    if v >= good:
        return "success"
    if v <= bad:
        return "error"
    return "warning"


def _render_plot(fig_json: dict[str, Any], *, height: int) -> None:
    with contextlib.suppress(Exception):
        import plotly.graph_objects as go

        fig = go.Figure(fig_json)
        fig.update_layout(height=height, margin={"l": 40, "r": 20, "t": 30, "b": 30})
        solara.FigurePlotly(fig)
