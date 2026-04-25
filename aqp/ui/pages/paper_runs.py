"""Paper Runs — list and drill into paper / live trading sessions.

Every row in the :class:`PaperTradingRun` table is surfaced here; pick one
to see live-updated KPIs, tabs for orders/fills/ledger, a Stop button
wired to ``/paper/stop/{task_id}``, and a launch form that kicks off a
new run from an inline YAML config.
"""
from __future__ import annotations

import json
from typing import Any

import solara
import yaml

from aqp.ui.api_client import post
from aqp.ui.components import (
    EntityTable,
    MetricTile,
    SplitPane,
    TabPanel,
    TabSpec,
    TaskStreamer,
    YamlEditor,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader

_DEFAULT_CONFIG = """\
name: paper-demo
session:
  run_name: paper-demo
  initial_cash: 100000.0
  max_bars: 500
  dry_run: true
  stop_on_kill_switch: true
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
"""


@solara.component
def Page() -> None:
    runs = use_api("/paper/runs?limit=30", default=[], interval=10.0)
    selected_id = solara.use_reactive("")
    detail = use_api(
        f"/paper/runs/{selected_id.value}" if selected_id.value else None,
        default={},
        interval=10.0 if selected_id.value else None,
    )
    launch_yaml = solara.use_reactive(_DEFAULT_CONFIG)
    run_name = solara.use_reactive("paper-demo")
    last_task_id = solara.use_reactive("")

    def _launch() -> None:
        try:
            cfg = yaml.safe_load(launch_yaml.value) or {}
            resp = post(
                "/paper/start",
                json={"config": cfg, "run_name": run_name.value or "paper-demo"},
            )
            last_task_id.set(resp.get("task_id", ""))
            runs.refresh()
        except Exception as exc:  # noqa: BLE001
            solara.Error(str(exc))

    def _stop() -> None:
        detail_val = detail.value or {}
        task_id = detail_val.get("task_id") or last_task_id.value
        if not task_id:
            solara.Warning("No active task id on the selected run.")
            return
        try:
            post(f"/paper/stop/{task_id}?reason=manual", json={})
            detail.refresh()
            runs.refresh()
        except Exception as exc:  # noqa: BLE001
            solara.Error(str(exc))

    PageHeader(
        title="Paper Trading Runs",
        subtitle=(
            "Start and monitor dry-run / live paper sessions. Orders + fills + "
            "ledger entries are correlated to each run via the standard "
            "``reference='paper:<run_id>'`` tag."
        ),
        icon="📝",
        actions=lambda: solara.Button(
            "Refresh", on_click=runs.refresh, outlined=True, dense=True
        ),
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        SplitPane(
            left_width="320px",
            left=lambda: _left_rail(
                runs=runs.value or [],
                selected_id=selected_id,
                launch_yaml=launch_yaml,
                run_name=run_name,
                on_launch=_launch,
                on_refresh=runs.refresh,
            ),
            right=lambda: _detail_pane(
                run=detail.value or {},
                last_task_id=last_task_id.value,
                on_stop=_stop,
            ),
        )


def _left_rail(
    *,
    runs: list[dict[str, Any]],
    selected_id: solara.Reactive[str],
    launch_yaml: solara.Reactive[str],
    run_name: solara.Reactive[str],
    on_launch,
    on_refresh,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Start a new paper run"):
            solara.InputText("run_name", value=run_name)
            with solara.Details(summary="Config YAML"):
                YamlEditor(
                    value=launch_yaml,
                    rows=14,
                    show_preview=False,
                )
            solara.Button("Start", on_click=on_launch, color="primary")
        with solara.Card("Sessions"):
            with solara.Row(gap="6px"):
                solara.Button("Refresh", on_click=on_refresh, outlined=True, dense=True)
            if not runs:
                solara.Markdown("_No paper runs yet._")
                return
            for r in runs:
                rid = r.get("id") or ""
                active = rid == selected_id.value
                status = (r.get("status") or "pending").lower()
                bg, fg = _STATUS_COLORS.get(status, ("#334155", "#cbd5e1"))
                with solara.Div(
                    style={
                        "background": bg,
                        "color": fg,
                        "padding": "10px 12px",
                        "border-radius": "8px",
                        "border-left": "3px solid #38bdf8"
                        if active
                        else "3px solid transparent",
                        "margin-bottom": "6px",
                    }
                ):
                    solara.Button(
                        label=f"{status.upper()} · {r.get('run_name') or rid[:8]}",
                        on_click=lambda i=rid: selected_id.set(i),
                        text=True,
                        dense=True,
                        style={"width": "100%", "text-align": "left", "color": fg},
                    )
                    solara.Markdown(
                        f"<div style='font-size:11px;opacity:0.75'>"
                        f"{r.get('brokerage', '?')} · {r.get('feed', '?')} · "
                        f"bars {r.get('bars_seen', 0)} · fills {r.get('fills', 0)}</div>"
                    )


_STATUS_COLORS = {
    "pending": ("#334155", "#cbd5e1"),
    "running": ("#1e3a8a", "#dbeafe"),
    "completed": ("#064e3b", "#bbf7d0"),
    "stopped": ("#78350f", "#fed7aa"),
    "error": ("#7f1d1d", "#fecaca"),
}


def _detail_pane(
    *,
    run: dict[str, Any],
    last_task_id: str,
    on_stop,
) -> None:
    if not run:
        with solara.Card():
            solara.Markdown("_Pick a session on the left — or start a new one._")
        if last_task_id:
            TaskStreamer(task_id=last_task_id, title="Worker stream")
        return

    _kpi_strip(run)
    with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
        status = (run.get("status") or "").lower()
        solara.Button(
            "Stop",
            on_click=on_stop,
            color="error",
            disabled=status not in {"running", "pending"},
        )

    task_id = run.get("task_id") or last_task_id
    if task_id:
        TaskStreamer(task_id=task_id, title="Worker stream", show_result=True)

    TabPanel(
        tabs=[
            TabSpec(
                key="orders",
                label="Orders",
                badge=len(run.get("recent_orders") or []),
                render=lambda: EntityTable(
                    rows=run.get("recent_orders") or [],
                    columns=["id", "vt_symbol", "side", "order_type", "quantity", "price", "status", "created_at"],
                    empty="_No orders._",
                ),
            ),
            TabSpec(
                key="fills",
                label="Fills",
                badge=len(run.get("recent_fills") or []),
                render=lambda: EntityTable(
                    rows=run.get("recent_fills") or [],
                    columns=["id", "vt_symbol", "side", "quantity", "price", "commission", "created_at"],
                    empty="_No fills._",
                ),
            ),
            TabSpec(
                key="ledger",
                label="Ledger",
                badge=len(run.get("recent_ledger") or []),
                render=lambda: EntityTable(
                    rows=run.get("recent_ledger") or [],
                    columns=["type", "level", "message", "created_at"],
                    empty="_No ledger entries._",
                ),
            ),
            TabSpec(
                key="config",
                label="Config",
                render=lambda: _config_tab(run.get("config") or {}),
            ),
            TabSpec(
                key="state",
                label="State",
                render=lambda: _state_tab(run.get("state") or {}),
            ),
        ]
    )


def _kpi_strip(run: dict[str, Any]) -> None:
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile("Run", run.get("run_name") or "—")
        MetricTile(
            "Status",
            (run.get("status") or "pending").upper(),
            tone=_status_tone(run.get("status")),
        )
        MetricTile("Bars seen", run.get("bars_seen", 0))
        MetricTile("Orders", run.get("orders_submitted", 0))
        MetricTile("Fills", run.get("fills", 0))
        MetricTile("Equity", run.get("final_equity"), unit="$")
        MetricTile("Realized PnL", run.get("realized_pnl"), unit="$")
        if run.get("max_drawdown") is not None:
            MetricTile(
                "Max Drawdown",
                run.get("max_drawdown"),
                unit="%",
                tone="error" if (run.get("max_drawdown") or 0) < -0.15 else "warning",
            )


def _status_tone(status: Any) -> str:
    if not status:
        return "neutral"
    s = str(status).lower()
    return {
        "running": "info",
        "completed": "success",
        "stopped": "warning",
        "error": "error",
    }.get(s, "neutral")


def _config_tab(config: dict[str, Any]) -> None:
    if not config:
        solara.Markdown("_No config snapshot._")
        return
    solara.Markdown(f"```yaml\n{yaml.safe_dump(config, sort_keys=False)}\n```")


def _state_tab(state: dict[str, Any]) -> None:
    if not state:
        solara.Markdown("_No state snapshot._")
        return
    solara.Markdown(f"```json\n{json.dumps(state, indent=2, default=str)}\n```")
