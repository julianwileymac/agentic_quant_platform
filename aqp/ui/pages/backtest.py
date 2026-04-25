"""Backtest Lab — kick off strategies and visualise results.

Enhanced in Phase 3C to add an **Agentic** tab when the selected run
has an :class:`aqp.persistence.models.AgentBacktest` sidecar. That tab
reuses :class:`aqp.ui.components.decision_timeline.DecisionTimeline`
and :class:`aqp.ui.components.debate_visualizer.DebateVisualizer` so
the user never has to leave this page to inspect trader-crew output.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import solara
import yaml

from aqp.ui.api_client import get, post
from aqp.ui.components.debate_visualizer import DebateVisualizer
from aqp.ui.components.decision_timeline import DecisionTimeline
from aqp.ui.components.layout import TabPanel, TabSpec

_STRAT_DIR = Path("configs/strategies")


@solara.component
def Page() -> None:
    available = solara.use_reactive(_list_configs())
    selected = solara.use_reactive(available.value[0] if available.value else "")
    editor = solara.use_reactive(_load_config(selected.value))
    runs = solara.use_reactive([])
    plot_kind = solara.use_reactive("equity")
    plot_id = solara.use_reactive("")
    plot_json = solara.use_reactive(None)
    sidecar = solara.use_reactive(None)
    crew_run_id = solara.use_reactive("")

    def refresh_configs() -> None:
        available.set(_list_configs())

    def load_cfg(name: str) -> None:
        selected.set(name)
        editor.set(_load_config(name))

    def refresh_runs() -> None:
        try:
            runs.set(get("/backtest/runs?limit=30") or [])
        except Exception:
            runs.set([])

    def run_backtest() -> None:
        try:
            cfg = yaml.safe_load(editor.value)
            r = post("/backtest/run", json={"config": cfg, "run_name": selected.value})
            solara.Info(f"Task queued: {r.get('task_id')}")
        except Exception as e:
            solara.Error(str(e))

    def fetch_plot() -> None:
        if not plot_id.value:
            return
        try:
            plot_json.set(get(f"/backtest/runs/{plot_id.value}/plot/{plot_kind.value}"))
        except Exception as e:
            plot_json.set({"error": str(e)})

    def fetch_sidecar() -> None:
        """Check if the selected run has an :class:`AgentBacktest` row."""
        if not plot_id.value:
            sidecar.set(None)
            return
        try:
            payload = get(f"/agentic/sidecar/{plot_id.value}")
            sidecar.set(payload)
        except Exception:
            sidecar.set(None)

    solara.use_effect(refresh_runs, [])
    solara.use_effect(fetch_sidecar, [plot_id.value])

    with solara.Column(gap="16px", style={"padding": "16px"}):
        solara.Markdown("# Backtest Lab")
        with solara.Row():
            solara.Select(label="Strategy recipe", value=selected, values=available.value, on_value=load_cfg)
            solara.Button("Reload configs", on_click=refresh_configs)
        solara.Markdown("### YAML editor")
        solara.InputTextArea("Config", value=editor, rows=20)
        solara.Button("Run backtest", on_click=run_backtest, color="primary")

        solara.Markdown("### Recent runs")
        solara.Button("Refresh runs", on_click=refresh_runs)
        if runs.value:
            df = pd.DataFrame(runs.value)
            solara.DataFrame(df, items_per_page=10)
        else:
            solara.Markdown("_No runs yet._")

        solara.Markdown("### Inspect a run")
        solara.InputText("Run id", value=plot_id)
        with solara.Row(gap="8px"):
            solara.Select(label="Kind", value=plot_kind, values=["equity", "drawdown"])
            solara.Button("Fetch plot", on_click=fetch_plot)

        def _render_performance() -> None:
            if plot_json.value:
                if "error" in plot_json.value:
                    solara.Error(plot_json.value["error"])
                else:
                    try:
                        import plotly.graph_objects as go

                        fig = go.Figure(plot_json.value)
                        solara.FigurePlotly(fig)
                    except Exception as e:
                        solara.Error(str(e))
            else:
                solara.Info("Pick a run id and click 'Fetch plot' to visualise equity / drawdown.", dense=True)

        def _render_agentic() -> None:
            info = sidecar.value
            if not info:
                solara.Info(
                    "This run has no trader-crew sidecar. "
                    "Kick off a run from the Agentic Quickstart wizard to see the Decision Timeline here.",
                    dense=True,
                )
                return

            with solara.Column(gap="10px"):
                solara.Markdown(
                    "#### Trader crew summary\n\n"
                    f"- **Mode:** `{info.get('mode', '-')}`\n"
                    f"- **Provider:** `{info.get('provider') or '(default)'}`\n"
                    f"- **Deep model:** `{info.get('deep_model') or '(default)'}`\n"
                    f"- **Quick model:** `{info.get('quick_model') or '(default)'}`\n"
                    f"- **Debate rounds:** `{info.get('max_debate_rounds', 1)}`\n"
                    f"- **Decisions:** `{info.get('n_decisions', 0)}`\n"
                    f"- **Total cost:** `${float(info.get('total_token_cost_usd') or 0):.4f}`\n"
                    f"- **Cache URI:** `{info.get('decision_cache_uri', '-')}`\n"
                )
                solara.Markdown("#### Decision timeline")
                DecisionTimeline(plot_id.value or None)
                solara.Markdown("#### Bull vs Bear debate")
                with solara.Row(gap="12px"):
                    solara.InputText(
                        "Crew run ID (copy from the timeline)",
                        value=crew_run_id,
                    )
                DebateVisualizer(crew_run_id.value or None)

        TabPanel(
            tabs=[
                TabSpec(key="perf", label="Performance", render=_render_performance, icon="📈"),
                TabSpec(
                    key="agentic",
                    label="Agentic",
                    render=_render_agentic,
                    icon="🧠",
                    badge="●" if sidecar.value else None,
                ),
            ],
        )


def _list_configs() -> list[str]:
    if not _STRAT_DIR.exists():
        return []
    return sorted(p.name for p in _STRAT_DIR.glob("*.yaml"))


def _load_config(name: str) -> str:
    if not name:
        return ""
    path = _STRAT_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
