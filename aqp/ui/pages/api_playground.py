"""API Playground — tabbed per-venue broker explorer.

Every venue surfaced at ``/brokers/*`` gets its own tab. Each tab shows a
status light plus one-click actions (query_account / query_positions),
with an order-submission form rendered by :class:`FormBuilder` so new
order types in the backend automatically surface in the UI.
"""
from __future__ import annotations

import json
from typing import Any

import solara

from aqp.ui.api_client import delete, get, post
from aqp.ui.components import (
    EntityTable,
    FieldSpec,
    FormBuilder,
    MetricTile,
    TabPanel,
    TabSpec,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader

ORDER_FIELDS: list[FieldSpec] = [
    FieldSpec("symbol", "Symbol", type="text", default="AAPL", group="Order"),
    FieldSpec(
        "side",
        "Side",
        type="enum",
        choices=["buy", "sell"],
        default="buy",
        group="Order",
    ),
    FieldSpec(
        "order_type",
        "Order type",
        type="enum",
        choices=["market", "limit", "stop", "stop_limit"],
        default="market",
        group="Order",
    ),
    FieldSpec("quantity", "Quantity", type="text", default="1", group="Order"),
    FieldSpec("price", "Limit price", type="text", default="", group="Optional"),
    FieldSpec("stop_price", "Stop price", type="text", default="", group="Optional"),
]


@solara.component
def Page() -> None:
    venues = use_api("/brokers/", default=[], interval=60.0)
    schema = use_api("/brokers/schema", default={})

    PageHeader(
        title="API Playground",
        subtitle=(
            "Interactively exercise the Alpaca, IBKR, Tradier, and simulated "
            "adapters through the unified ``IBrokerage`` surface."
        ),
        icon="🧾",
        actions=lambda: solara.Button("Refresh venues", on_click=venues.refresh, outlined=True, dense=True),
    )

    rows = venues.value or []
    names = [v.get("name") for v in rows if v.get("name")]
    if not names:
        with solara.Column(style={"padding": "20px"}):
            solara.Markdown("_Loading venues…_ ")
        return

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        _kpi_strip(rows)
        TabPanel(
            tabs=[
                TabSpec(
                    key=str(name),
                    label=str(name),
                    render=lambda name=name: _venue_tab(name, rows, schema.value or {}),
                )
                for name in names
            ]
        )


def _kpi_strip(rows: list[dict[str, Any]]) -> None:
    available = sum(1 for v in rows if v.get("available"))
    configured = sum(1 for v in rows if v.get("configured"))
    paper = sum(1 for v in rows if v.get("paper"))
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile("Venues", len(rows))
        MetricTile(
            "SDK available",
            available,
            tone="success" if available else "warning",
        )
        MetricTile(
            "Credentials",
            configured,
            tone="success" if configured else "warning",
        )
        MetricTile("Paper-mode", paper, tone="info" if paper else "neutral")


def _venue_tab(
    venue_name: str, rows: list[dict[str, Any]], schema: dict[str, Any]
) -> None:
    info = next((v for v in rows if v.get("name") == venue_name), {})
    status = use_api(f"/brokers/{venue_name}/status", default={}, interval=None, auto=False)
    account = use_api(f"/brokers/{venue_name}/account", default={}, interval=None, auto=False)
    positions = use_api(f"/brokers/{venue_name}/positions", default=[], interval=None, auto=False)

    last_response: solara.Reactive[str] = solara.use_reactive("")

    def _submit_order(form_values: dict[str, Any]) -> None:
        body = {
            k: v for k, v in form_values.items() if v not in ("", None)
        }
        for numeric_key in ("quantity", "price", "stop_price"):
            if numeric_key in body:
                try:
                    body[numeric_key] = float(body[numeric_key])
                except (TypeError, ValueError):
                    body.pop(numeric_key, None)
        try:
            resp = post(f"/brokers/{venue_name}/orders", json=body)
            last_response.set(_fmt(resp))
            solara.Info(f"Order accepted: {resp.get('order_id')}")
        except Exception as exc:  # noqa: BLE001
            last_response.set(f"error: {exc}")
            solara.Error(str(exc))

    cancel_id = solara.use_reactive("")

    def _cancel_order() -> None:
        oid = cancel_id.value.strip()
        if not oid:
            return
        try:
            resp = delete(f"/brokers/{venue_name}/orders/{oid}")
            last_response.set(_fmt(resp))
            if resp.get("cancelled"):
                solara.Info(f"Cancelled {oid}")
        except Exception as exc:  # noqa: BLE001
            last_response.set(str(exc))
            solara.Error(str(exc))

    with solara.Column(gap="12px"):
        _venue_header(info, status)
        _actions_row(status, account, positions)
        _body_panels(account.value, positions.value)
        _order_card(info, _submit_order)
        _cancel_card(cancel_id, _cancel_order)
        if last_response.value:
            with solara.Card("Last response"):
                solara.Markdown(f"```json\n{last_response.value}\n```")
        if schema.get("methods"):
            with solara.Card("IBrokerage methods"):
                EntityTable(
                    rows=schema.get("methods", []),
                    columns=["name", "readonly", "description"],
                    searchable=False,
                )


def _venue_header(info: dict[str, Any], status) -> None:
    ok = status.value.get("ok") if status.value else None
    if ok is True:
        tone = "success"
        label = "ONLINE"
    elif ok is False:
        tone = "error"
        label = "OFFLINE"
    else:
        tone = "neutral"
        label = "UNKNOWN"
    with solara.Card(info.get("name", "?")):
        with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
            MetricTile(
                "Status",
                label,
                tone=tone,
                hint=status.value.get("error") or "",
            )
            MetricTile(
                "SDK",
                "installed" if info.get("available") else "missing",
                tone="success" if info.get("available") else "warning",
                hint=", ".join(info.get("missing_extras") or []) or "—",
            )
            MetricTile(
                "Credentials",
                "configured" if info.get("configured") else "none",
                tone="success" if info.get("configured") else "error",
            )
            MetricTile("Paper mode", info.get("paper"), tone="info" if info.get("paper") else "neutral")
        if info.get("description"):
            solara.Markdown(f"_{info['description']}_")


def _actions_row(status, account, positions) -> None:
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        solara.Button("Probe status", on_click=status.refresh, color="primary", outlined=True, dense=True)
        solara.Button("query_account", on_click=account.refresh, dense=True, outlined=True)
        solara.Button("query_positions", on_click=positions.refresh, dense=True, outlined=True)


def _body_panels(account: dict[str, Any], positions: list[dict[str, Any]]) -> None:
    if account:
        with solara.Card("Account"):
            solara.Markdown(f"```json\n{_fmt(account)}\n```")
    if positions:
        EntityTable(
            rows=positions,
            columns=[
                "vt_symbol",
                "direction",
                "quantity",
                "average_price",
                "unrealized_pnl",
                "realized_pnl",
            ],
            title="Positions",
            empty="_No positions._",
        )


def _order_card(info: dict[str, Any], on_submit) -> None:
    with solara.Card("Submit order"):
        solara.Markdown(
            "_Orders honour the global kill switch; submission goes through "
            "the venue's ``submit_order`` path."
        )
        form = FormBuilder(fields=ORDER_FIELDS)
        solara.Button(
            "Submit order",
            on_click=lambda: on_submit(form.values),
            color="warning",
            disabled=not info.get("available") or not info.get("configured"),
        )


def _cancel_card(cancel_id: solara.Reactive[str], on_cancel) -> None:
    with solara.Card("Cancel order"):
        solara.InputText("order_id", value=cancel_id)
        solara.Button("Cancel", on_click=on_cancel)


def _fmt(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)
