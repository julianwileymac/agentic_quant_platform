"""Decision timeline component — renders agent decisions alongside equity.

Consumes the ``GET /agentic/decisions/{backtest_id}`` response and
renders a scrollable table with action badges (BUY / SELL / HOLD),
rating chips, rationale, confidence, and token cost. Used by the
Backtest Lab's Agentic tab and by the Quickstart Wizard's results
step.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import solara

from aqp.ui.components.data.use_api import use_api

_ACTION_COLORS = {
    "BUY": "#22c55e",
    "SELL": "#ef4444",
    "HOLD": "#94a3b8",
}

_RATING_COLORS = {
    "strong_buy": "#16a34a",
    "buy": "#22c55e",
    "hold": "#94a3b8",
    "sell": "#ef4444",
    "strong_sell": "#dc2626",
}


def _format_ts(ts: Any) -> str:
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return ts
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d")
    return str(ts)


def _action_badge(action: str) -> None:
    color = _ACTION_COLORS.get(action.upper(), "#94a3b8")
    solara.Div(
        children=[solara.Text(action.upper())],
        style={
            "padding": "2px 10px",
            "border-radius": "12px",
            "background": color,
            "color": "white",
            "font-weight": "700",
            "font-size": "0.78em",
            "letter-spacing": "0.03em",
            "text-align": "center",
        },
    )


def _rating_chip(rating: str) -> None:
    color = _RATING_COLORS.get(rating.lower(), "#64748b")
    pretty = rating.replace("_", " ").title()
    solara.Div(
        children=[solara.Text(pretty)],
        style={
            "padding": "1px 8px",
            "border-radius": "10px",
            "border": f"1px solid {color}",
            "color": color,
            "font-weight": "600",
            "font-size": "0.75em",
        },
    )


@solara.component
def DecisionTimeline(backtest_id: str | None, limit: int = 500) -> None:
    """Render the agent-decision timeline for one backtest.

    When ``backtest_id`` is falsy we render a friendly hint instead of
    firing a bad API call, so callers can mount the component before the
    run finishes.
    """
    if not backtest_id:
        solara.Info("Submit a backtest to see the decision timeline.", dense=True)
        return

    result = use_api(
        f"/agentic/decisions/{backtest_id}?limit={limit}",
        default=[],
    )
    if result.loading:
        solara.Info("Loading decisions…", dense=True)
        return
    if result.error:
        solara.Error(f"Failed to load decisions: {result.error}", dense=True)
        return

    rows: list[dict[str, Any]] = list(result.value or [])
    if not rows:
        solara.Info(
            "No decisions recorded for this backtest. Check that the "
            "precompute task completed and the sidecar row was written.",
            dense=True,
        )
        return

    with solara.Column(gap="8px", style={"flex": "1", "min-width": "0"}):
        _render_summary(rows)
        _render_header_row()
        with solara.Div(
            style={
                "max-height": "480px",
                "overflow-y": "auto",
                "padding-right": "6px",
            }
        ):
            for row in rows:
                _render_decision_row(row)


def _render_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    n_buy = sum(1 for r in rows if str(r.get("action", "")).upper() == "BUY")
    n_sell = sum(1 for r in rows if str(r.get("action", "")).upper() == "SELL")
    n_hold = total - n_buy - n_sell
    total_cost = sum(float(r.get("token_cost_usd") or 0) for r in rows)
    with solara.Row(gap="16px", style={"flex-wrap": "wrap", "margin-bottom": "4px"}):
        solara.Markdown(f"**Decisions:** {total}")
        solara.Markdown(f"**Buys:** {n_buy}")
        solara.Markdown(f"**Sells:** {n_sell}")
        solara.Markdown(f"**Holds:** {n_hold}")
        solara.Markdown(f"**Total cost:** ${total_cost:.3f}")


_GRID_STYLE = {
    "display": "grid",
    "grid-template-columns": "110px 110px 80px 80px 110px 1fr 90px",
    "gap": "10px",
    "align-items": "center",
    "padding": "6px 4px",
    "border-bottom": "1px solid rgba(148,163,184,0.12)",
}


def _render_header_row() -> None:
    labels = ["Date", "Symbol", "Action", "Size", "Rating", "Rationale", "Cost USD"]
    with solara.Div(
        style={
            **_GRID_STYLE,
            "font-weight": "700",
            "border-bottom": "1px solid rgba(148,163,184,0.35)",
            "color": "rgba(226,232,240,0.9)",
            "font-size": "0.78em",
            "letter-spacing": "0.03em",
            "text-transform": "uppercase",
        }
    ):
        for label in labels:
            solara.Text(label)


def _render_decision_row(row: dict[str, Any]) -> None:
    with solara.Div(style=_GRID_STYLE):
        solara.Text(_format_ts(row.get("ts") or ""), style={"font-variant-numeric": "tabular-nums"})
        solara.Text(
            str(row.get("vt_symbol", "")),
            style={"font-weight": "600"},
        )
        _action_badge(str(row.get("action", "HOLD")))
        solara.Text(
            f"{float(row.get('size_pct') or 0) * 100:.1f}%",
            style={"font-variant-numeric": "tabular-nums"},
        )
        _rating_chip(str(row.get("rating", "hold")))
        rationale = str(row.get("rationale") or "")
        solara.Text(
            rationale if len(rationale) <= 140 else rationale[:137] + "…",
            style={
                "color": "rgba(226,232,240,0.85)",
                "font-size": "0.92em",
            },
        )
        solara.Text(
            f"${float(row.get('token_cost_usd') or 0):.4f}",
            style={
                "color": "rgba(148,163,184,0.9)",
                "font-variant-numeric": "tabular-nums",
                "text-align": "right",
            },
        )
