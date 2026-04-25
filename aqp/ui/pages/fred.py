"""FRED Explorer — search FRED series and preview observations."""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara

from aqp.ui.api_client import get, post


@solara.component
def Page() -> None:
    query = solara.use_reactive("inflation")
    results: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    selected_id = solara.use_reactive("")
    observations: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    ingest_task = solara.use_reactive("")
    error = solara.use_reactive("")

    def search() -> None:
        if not query.value.strip():
            return
        try:
            payload = get(f"/fred/series/search", params={"q": query.value.strip(), "limit": 25})
            results.set(list(payload.get("results") or []))
            error.set("")
        except Exception as exc:  # pragma: no cover
            results.set([])
            error.set(str(exc))

    def preview(series_id: str) -> None:
        selected_id.set(series_id)
        try:
            payload = get(
                f"/fred/series/{series_id}/observations",
                params={"limit": 500, "persist": False},
            )
            observations.set(list(payload.get("observations") or []))
            error.set("")
        except Exception as exc:  # pragma: no cover
            observations.set([])
            error.set(str(exc))

    def ingest(series_id: str) -> None:
        try:
            r = post("/fred/ingest", json={"series_ids": [series_id]})
            ingest_task.set(str(r.get("task_id", "")))
        except Exception as exc:  # pragma: no cover
            error.set(str(exc))

    with solara.Column(gap="12px", style={"padding": "16px", "max-width": "1200px"}):
        solara.Markdown("# FRED Explorer")
        solara.Markdown(
            "Search the Federal Reserve Economic Data catalog. Requires "
            "`AQP_FRED_API_KEY` and the `[fred]` optional extra."
        )
        with solara.Row():
            solara.InputText(label="Search text", value=query)
            solara.Button("Search", on_click=search, color="primary")
        if error.value:
            solara.Error(error.value)
        if ingest_task.value:
            solara.Info(f"Ingest task queued: {ingest_task.value}")

        for row in results.value:
            series_id = row.get("series_id") or ""
            with solara.Card(style={"padding": "12px"}):
                solara.Markdown(
                    f"**{series_id}** — {row.get('title', '')}  "
                    f"*{row.get('frequency_short', '')}, {row.get('units_short', '')}*"
                )
                with solara.Row():
                    solara.Button(
                        "Preview last 500",
                        on_click=lambda sid=series_id: preview(sid),
                    )
                    solara.Button(
                        "Ingest into lake",
                        on_click=lambda sid=series_id: ingest(sid),
                    )

        if selected_id.value and observations.value:
            solara.Markdown(f"## Observations — {selected_id.value}")
            df = pd.DataFrame(observations.value)
            solara.DataFrame(df)
