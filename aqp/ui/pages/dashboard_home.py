"""Dashboard Home — the new landing page.

Replaces the old text-wall welcome with a Bento-grid of live platform
telemetry: KPIs from ``/portfolio/*``, latest backtest runs, kill-switch
card, broker venue status, and quick-launch tiles into the major sections.
"""
from __future__ import annotations

from typing import Any

import solara

from aqp.ui.components import (
    CardGrid,
    EntityTable,
    MetricTile,
    TileTrend,
    use_api,
)
from aqp.ui.components.layout.card_grid import CardSpec
from aqp.ui.layout.page_header import PageHeader

QUICK_LINKS: list[tuple[str, str, str]] = [
    ("Chat with the quant assistant", "/chat", "mdi-chat-processing"),
    ("Compose a strategy", "/strategy", "mdi-flask"),
    ("Browse saved strategies", "/strategy-browser", "mdi-folder-search"),
    ("Run a backtest", "/backtest", "mdi-play-circle"),
    ("Watch live market", "/live", "mdi-chart-timeline"),
    ("Sweep parameters", "/optimizer", "mdi-tune-variant"),
    ("Monitor trades", "/monitor", "mdi-monitor-dashboard"),
    ("Crew trace", "/crew", "mdi-account-group"),
]


@solara.component
def Page() -> None:
    ks = use_api("/portfolio/kill_switch", default={}, interval=15.0)
    orders = use_api("/portfolio/orders?limit=1", default=[], interval=15.0)
    runs = use_api("/backtest/runs?limit=5", default=[], interval=20.0)
    paper = use_api("/paper/runs?limit=5", default=[], interval=20.0)
    venues = use_api("/brokers/", default=[], interval=60.0)

    PageHeader(
        title="Dashboard",
        subtitle="Live snapshot of the platform — kill switch, recent work, quick launchers.",
        icon="🧭",
    )

    with solara.Column(gap="18px", style={"padding": "18px 22px"}):
        _kpi_strip(ks.value or {}, orders.value or [], runs.value or [], paper.value or [])

        CardGrid(
            [
                CardSpec(
                    key="runs",
                    title="Latest backtest runs",
                    span=2,
                    render=lambda: _runs_table(runs.value or []),
                ),
                CardSpec(
                    key="paper",
                    title="Paper / live trading",
                    span=2,
                    render=lambda: _paper_table(paper.value or []),
                ),
                CardSpec(
                    key="venues",
                    title="Broker venues",
                    span=2,
                    render=lambda: _venues_block(venues.value or []),
                ),
                CardSpec(
                    key="quick",
                    title="Quick launch",
                    span=2,
                    render=_quick_launch,
                ),
            ],
            columns=4,
            gap="14px",
        )


def _kpi_strip(
    ks: dict[str, Any],
    orders: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    paper_runs: list[dict[str, Any]],
) -> None:
    engaged = bool(ks.get("engaged"))
    total_orders = len(orders)
    latest_sharpe = (runs[0].get("sharpe") if runs else None) if runs else None
    active_paper = [r for r in paper_runs if r.get("status") == "running"]
    with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
        MetricTile(
            "Kill switch",
            "ENGAGED" if engaged else "Released",
            tone="error" if engaged else "success",
            hint=str(ks.get("reason") or "—"),
        )
        MetricTile(
            "Recent orders",
            total_orders,
            hint="last 1 visible" if total_orders else "none",
            tone="info" if total_orders else "neutral",
        )
        MetricTile(
            "Latest Sharpe",
            latest_sharpe,
            trend=TileTrend(delta=0, label="") if latest_sharpe is None else None,
            tone=_sharpe_tone(latest_sharpe),
        )
        MetricTile(
            "Active paper runs",
            len(active_paper),
            hint=f"{len(paper_runs)} total",
            tone="info" if active_paper else "neutral",
        )


def _runs_table(rows: list[dict[str, Any]]) -> None:
    EntityTable(
        rows=rows,
        columns=["id", "status", "sharpe", "total_return", "max_drawdown", "created_at"],
        searchable=False,
        empty="_No backtests yet — run one in the Backtest Lab._",
    )


def _paper_table(rows: list[dict[str, Any]]) -> None:
    EntityTable(
        rows=rows,
        columns=[
            "id",
            "run_name",
            "status",
            "brokerage",
            "bars_seen",
            "fills",
            "realized_pnl",
        ],
        searchable=False,
        empty="_No paper runs — start one from the Paper Trading page._",
    )


def _venues_block(rows: list[dict[str, Any]]) -> None:
    if not rows:
        solara.Markdown("_Loading venues…_")
        return
    with solara.Column(gap="4px"):
        for v in rows:
            name = v.get("name") or "—"
            ok = bool(v.get("available") and v.get("configured"))
            bg = "#064e3b" if ok else "#7f1d1d"
            chip = (
                f"<span style='background:{bg};color:#f8fafc;padding:2px 8px;"
                "border-radius:999px;font-size:10px;margin-right:8px'>"
                f"{'READY' if ok else 'OFF'}</span>"
            )
            desc = v.get("description") or ""
            solara.Markdown(f"{chip}**{name}** — <span style='opacity:0.7'>{desc}</span>")


def _quick_launch() -> None:
    with solara.Column(gap="6px"):
        for label, href, glyph in QUICK_LINKS:
            solara.HTML(
                tag="a",
                unsafe_innerHTML=f"<span style='opacity:0.9'>{glyph or '•'}</span>&nbsp;&nbsp;{label}",
                attributes={
                    "href": href,
                    "style": (
                        "display:block;padding:6px 10px;border-radius:8px;"
                        "text-decoration:none;color:#e2e8f0;font-size:13px;"
                        "background:rgba(148, 163, 184, 0.08)"
                    ),
                },
            )


def _sharpe_tone(value: Any) -> str:
    if value is None:
        return "neutral"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if v >= 1.0:
        return "success"
    if v <= 0:
        return "error"
    return "warning"
