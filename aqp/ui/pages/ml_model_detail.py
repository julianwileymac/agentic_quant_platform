"""ML Models — list + detail view (metrics, feature importance, predictions).

Left rail lists every persisted :class:`ModelVersion` row from
``/ml/models``. Right pane loads ``/ml/models/{id}/details`` — a
StatsGrid, a feature-importance bar chart, a predictions preview table,
and dataset lineage metadata.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara

from aqp.ui.components import (
    EntityTable,
    MetricTile,
    SplitPane,
    StatsGrid,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader


@solara.component
def Page() -> None:
    selected_id = solara.use_reactive("")
    registry_filter = solara.use_reactive("")

    models = use_api(
        f"/ml/models?limit=100{('&registry_name=' + registry_filter.value) if registry_filter.value.strip() else ''}",
        default=[],
        interval=None,
    )
    detail = use_api(
        f"/ml/models/{selected_id.value}/details" if selected_id.value else None,
        default={},
    )

    PageHeader(
        title="ML Models",
        subtitle=(
            "Registered model versions with metrics, feature importance, "
            "prediction samples, and MLflow lineage."
        ),
        icon="🧬",
        actions=lambda: solara.Button(
            "Refresh",
            on_click=models.refresh,
            outlined=True,
            dense=True,
        ),
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        SplitPane(
            left_width="320px",
            left=lambda: _left_rail(
                models=models.value or [],
                registry_filter=registry_filter,
                selected_id=selected_id,
                on_refresh=models.refresh,
            ),
            right=lambda: _detail_pane(
                loading=detail.loading,
                error=detail.error,
                detail=detail.value or {},
            ),
        )


def _left_rail(
    *,
    models: list[dict[str, Any]],
    registry_filter: solara.Reactive[str],
    selected_id: solara.Reactive[str],
    on_refresh,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Filter"):
            solara.InputText("Registry name contains…", value=registry_filter)
            solara.Button("Apply", on_click=on_refresh, outlined=True)
        with solara.Card("Models"):
            if not models:
                solara.Markdown("_No models registered yet._")
                return
            for m in models:
                mid = m.get("id") or ""
                active = mid == selected_id.value
                name = m.get("registry_name") or "?"
                algo = m.get("algo") or "—"
                stage = m.get("stage") or "None"
                bg = "#1e3a8a" if active else "rgba(148,163,184,0.08)"
                fg = "#f8fafc" if active else "#cbd5e1"
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
                        label=name,
                        on_click=lambda i=mid: selected_id.set(i),
                        text=True,
                        dense=True,
                        style={"width": "100%", "text-align": "left"},
                    )
                    solara.Markdown(
                        f"<div style='font-size:11px;opacity:0.75'>"
                        f"{algo} · {stage} · v{m.get('mlflow_version', '?')}</div>"
                    )


def _detail_pane(
    *,
    loading: bool,
    error: str,
    detail: dict[str, Any],
) -> None:
    if loading:
        with solara.Card():
            solara.Markdown("_Loading…_")
        return
    if error:
        solara.Error(error)
        return
    if not detail:
        with solara.Card():
            solara.Markdown("_Pick a model on the left._")
        return

    summary = detail.get("summary") or {}
    metrics = detail.get("metrics") or {}
    importance = detail.get("feature_importance") or []
    predictions = detail.get("predictions") or []
    lineage = detail.get("lineage") or {}

    _kpi_strip(summary)
    _metrics_card(metrics)
    _importance_card(importance)
    _predictions_card(predictions)
    _lineage_card(lineage)


def _kpi_strip(summary: dict[str, Any]) -> None:
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile("Model", summary.get("registry_name"))
        MetricTile("Algo", summary.get("algo") or "—")
        MetricTile("Stage", summary.get("stage") or "None")
        MetricTile("MLflow v", summary.get("mlflow_version") or "—")
        MetricTile(
            "Created",
            (summary.get("created_at") or "")[:10] if summary.get("created_at") else "—",
        )


def _metrics_card(metrics: dict[str, Any]) -> None:
    if not metrics:
        return
    with solara.Card("Metrics"):
        numeric = {
            k: v
            for k, v in metrics.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        non_numeric = {k: v for k, v in metrics.items() if k not in numeric}
        if numeric:
            StatsGrid(numeric, columns=4)
        if non_numeric:
            with solara.Details(summary="Other metadata"):
                for k, v in non_numeric.items():
                    solara.Markdown(f"- **{k}**: `{v}`")


def _importance_card(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with solara.Card("Feature importance"):
        EntityTable(
            rows=rows,
            columns=["name", "importance"],
            title=f"Top {len(rows)}",
            searchable=True,
            items_per_page=15,
        )
        try:
            import plotly.graph_objects as go

            df = pd.DataFrame(rows)
            df = df.sort_values("importance", key=lambda s: s.abs(), ascending=True).tail(20)
            fig = go.Figure(
                data=go.Bar(x=df["importance"], y=df["name"], orientation="h")
            )
            fig.update_layout(
                title="Top features (abs importance)",
                height=min(480, 30 * len(df) + 60),
                margin={"l": 130, "r": 20, "t": 30, "b": 30},
            )
            solara.FigurePlotly(fig)
        except Exception:
            pass


def _predictions_card(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with solara.Card("Predictions preview"):
        EntityTable(
            rows=rows,
            title=f"{len(rows)} recent predictions",
            searchable=True,
        )


def _lineage_card(lineage: dict[str, Any]) -> None:
    with solara.Card("Lineage"):
        solara.Markdown(
            f"- **Dataset hash**: `{lineage.get('dataset_hash') or '—'}`\n"
            f"- **MLflow run**: `{lineage.get('mlflow_run_id') or '—'}`"
        )
