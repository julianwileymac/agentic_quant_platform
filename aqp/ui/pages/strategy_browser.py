"""Strategy Browser — browsable catalog of saved strategies + code-available alphas.

Two panes:

1. **Saved strategies** — calls ``GET /strategies/browse`` with filters.
   Click a row to inspect versions, tests, and the latest equity curve.
2. **Alpha catalog** — calls ``GET /strategies/browse/catalog`` to list every
   concrete ``IAlphaModel`` class we can instantiate, tags, and any
   reference YAMLs shipped in ``configs/strategies/``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara

from aqp.ui.api_client import api_url, get


@solara.component
def Page() -> None:
    rows = solara.use_reactive([])
    catalog = solara.use_reactive([])
    selected_tag = solara.use_reactive("(any)")
    search = solara.use_reactive("")
    min_sharpe = solara.use_reactive(0.0)
    detail_id = solara.use_reactive("")
    detail = solara.use_reactive(None)
    equity = solara.use_reactive(None)

    def refresh_rows() -> None:
        q = "?limit=100"
        if selected_tag.value and selected_tag.value != "(any)":
            q += f"&tag={selected_tag.value}"
        if search.value:
            q += f"&query={search.value}"
        if min_sharpe.value:
            q += f"&min_sharpe={min_sharpe.value}"
        try:
            rows.set(get(f"/strategies/browse{q}") or [])
        except Exception:
            rows.set([])

    def refresh_catalog() -> None:
        try:
            catalog.set(get("/strategies/browse/catalog") or [])
        except Exception:
            catalog.set([])

    def open_detail(row: dict[str, Any]) -> None:
        detail_id.set(row["id"])
        try:
            detail.set(get(f"/strategies/{row['id']}"))
        except Exception:
            detail.set(None)
        mlflow_run = row.get("latest_mlflow_run_id")
        equity.set(None)
        if mlflow_run:
            # Try the backtest equity-curve endpoint via mlflow_run -> backtest row.
            try:
                runs = get(f"/strategies/{row['id']}/experiment").get("runs", [])
                if runs:
                    bt_id = runs[0]["id"]
                    equity.set(get(f"/backtest/runs/{bt_id}/plot/equity"))
            except Exception:
                equity.set(None)

    def tag_options(cat: list[dict[str, Any]]) -> list[str]:
        tags = sorted({t for row in cat for t in row.get("tags", [])})
        return ["(any)", *tags]

    solara.use_effect(refresh_rows, [])
    solara.use_effect(refresh_catalog, [])

    with solara.Column(gap="18px", style={"padding": "18px"}):
        solara.Markdown("# Strategy Browser")
        solara.Markdown(
            "Browse every strategy you've saved in AQP, filter by tag / Sharpe / name search, and deep-link "
            "into the underlying MLflow experiment."
        )

        with solara.Row(gap="12px"):
            solara.Select(
                label="Tag filter",
                value=selected_tag,
                values=tag_options(catalog.value),
            )
            solara.InputText("Name search", value=search)
            solara.InputFloat("Min Sharpe", value=min_sharpe)
            solara.Button("Refresh", on_click=refresh_rows, color="primary")
            solara.Button("Reload catalog", on_click=refresh_catalog)

        solara.Markdown("### Saved strategies")
        if rows.value:
            df = pd.DataFrame(rows.value)
            display_cols = [
                c
                for c in (
                    "name",
                    "status",
                    "alpha_class",
                    "engine",
                    "last_sharpe",
                    "last_total_return",
                    "last_max_drawdown",
                    "last_tested_at",
                    "tags",
                )
                if c in df.columns
            ]
            solara.DataFrame(df[display_cols], items_per_page=25)
            solara.Markdown("#### Open a strategy")
            with solara.Row(gap="12px"):
                solara.InputText("Strategy id", value=detail_id)
                solara.Button(
                    "Open",
                    on_click=lambda: open_detail(
                        next((r for r in rows.value if r.get("id") == detail_id.value), {"id": detail_id.value})
                    ),
                )
        else:
            solara.Markdown("_No strategies saved yet — compose one in the Strategy Development page._")

        if detail.value:
            with solara.Card(title=detail.value.get("name")):
                solara.Markdown(
                    f"- **Version**: {detail.value.get('version')}  \n"
                    f"- **Author**: {detail.value.get('author')}  \n"
                    f"- **Status**: {detail.value.get('status')}  \n"
                    f"- **MLflow experiment**: `strategy/{detail.value.get('id', '')[:8]}`"
                )
                solara.Markdown("#### Versions")
                if detail.value.get("versions"):
                    solara.DataFrame(pd.DataFrame(detail.value["versions"]), items_per_page=10)
                solara.Markdown("#### Recent tests")
                if detail.value.get("tests"):
                    solara.DataFrame(pd.DataFrame(detail.value["tests"]), items_per_page=10)
                if equity.value and "data" in equity.value:
                    try:
                        import plotly.graph_objects as go

                        fig = go.Figure(equity.value)
                        solara.FigurePlotly(fig)
                    except Exception:
                        pass
                solara.Markdown(
                    f"[Open MLflow experiment]({api_url('/strategies/' + detail.value.get('id', '') + '/experiment')})"
                )

        solara.Markdown("### Alpha catalog (code-available)")
        if catalog.value:
            cat_df = pd.DataFrame(catalog.value)
            cat_df["config_paths"] = cat_df["config_paths"].apply(lambda v: ", ".join(v) if v else "")
            cat_df["tags"] = cat_df["tags"].apply(lambda v: ", ".join(v) if v else "")
            solara.DataFrame(cat_df, items_per_page=25)
        else:
            solara.Markdown("_No alpha classes resolved — is the backend running?_")
