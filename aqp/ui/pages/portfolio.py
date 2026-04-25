"""Portfolio & Ledger — KPI strip + tabbed Orders / Fills / Ledger panels.

The old page was a vertical wall of four ``DataFrame`` tables. This
refactor uses :class:`MetricTile` for quick-glance KPIs, a single
``TabPanel`` for the tables (so scrolling doesn't compete), and keeps
the kill-switch card pinned at the top as its own action.
"""
from __future__ import annotations

from typing import Any

import solara

from aqp.ui.api_client import post
from aqp.ui.components import (
    EntityTable,
    MetricTile,
    TabPanel,
    TabSpec,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader


@solara.component
def Page() -> None:
    orders = use_api("/portfolio/orders?limit=100", default=[], interval=10.0)
    fills = use_api("/portfolio/fills?limit=100", default=[], interval=10.0)
    ledger = use_api("/portfolio/ledger?limit=200", default=[], interval=10.0)
    ks = use_api("/portfolio/kill_switch", default={}, interval=15.0)

    ks_reason = solara.use_reactive("manual intervention")

    def _engage() -> None:
        post(
            "/portfolio/kill_switch",
            json={"reason": ks_reason.value, "engage": True},
        )
        ks.refresh()

    def _release() -> None:
        post(
            "/portfolio/kill_switch",
            json={"reason": "", "engage": False},
        )
        ks.refresh()

    def _refresh_all() -> None:
        orders.refresh()
        fills.refresh()
        ledger.refresh()
        ks.refresh()

    PageHeader(
        title="Portfolio",
        subtitle="Kill switch, orders, fills, and the execution ledger — all live.",
        icon="💼",
        actions=lambda: solara.Button("Refresh", on_click=_refresh_all, outlined=True, dense=True),
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        _kpi_strip(ks.value or {}, orders.value or [], fills.value or [])
        _kill_switch_card(ks.value or {}, ks_reason, _engage, _release)
        TabPanel(
            tabs=[
                TabSpec(
                    key="orders",
                    label="Orders",
                    badge=len(orders.value or []),
                    render=lambda: EntityTable(
                        rows=orders.value or [],
                        columns=[
                            "id",
                            "vt_symbol",
                            "side",
                            "order_type",
                            "quantity",
                            "price",
                            "status",
                            "created_at",
                        ],
                        empty="_No orders yet._",
                    ),
                ),
                TabSpec(
                    key="fills",
                    label="Fills",
                    badge=len(fills.value or []),
                    render=lambda: EntityTable(
                        rows=fills.value or [],
                        columns=[
                            "id",
                            "vt_symbol",
                            "side",
                            "quantity",
                            "price",
                            "commission",
                            "slippage",
                            "created_at",
                        ],
                        empty="_No fills yet._",
                    ),
                ),
                TabSpec(
                    key="ledger",
                    label="Ledger",
                    badge=len(ledger.value or []),
                    render=lambda: _ledger_tab(ledger.value or []),
                ),
            ]
        )


def _kpi_strip(
    ks: dict[str, Any],
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> None:
    engaged = bool(ks.get("engaged"))
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile(
            "Kill switch",
            "ENGAGED" if engaged else "Released",
            tone="error" if engaged else "success",
            hint=str(ks.get("reason") or "—"),
        )
        MetricTile("Open orders", sum(1 for o in orders if (o.get("status") or "").lower() not in {"filled", "cancelled", "rejected"}))
        MetricTile("Fills today", len(fills))
        MetricTile("Last order", (orders[0].get("vt_symbol") if orders else "—"))


def _kill_switch_card(
    ks: dict[str, Any],
    ks_reason: solara.Reactive[str],
    on_engage,
    on_release,
) -> None:
    with solara.Card("Kill switch"):
        engaged = bool(ks.get("engaged"))
        badge = "🛑 ENGAGED" if engaged else "🟢 released"
        solara.Markdown(f"**Status:** {badge}  \nReason: `{ks.get('reason') or '-'}`")
        solara.InputText("Reason", value=ks_reason)
        with solara.Row(gap="6px"):
            solara.Button("Engage", on_click=on_engage, color="error")
            solara.Button("Release", on_click=on_release, color="success")


def _ledger_tab(ledger: list[dict[str, Any]]) -> None:
    entry_types = sorted({r.get("type") for r in ledger if r.get("type")})
    selected = solara.use_reactive("(all)")
    options = ["(all)", *entry_types]
    with solara.Column(gap="8px"):
        with solara.Row(gap="10px"):
            solara.Select(label="Entry type", value=selected, values=options)
        rows = ledger if selected.value == "(all)" else [
            r for r in ledger if (r.get("type") or "").lower() == selected.value.lower()
        ]
        EntityTable(
            rows=rows,
            columns=["type", "level", "message", "created_at"],
            empty="_Ledger empty._",
            items_per_page=20,
        )
