"""GDelt Explorer — inspect the manifest, ingest a window, browse mentions."""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara

from aqp.ui.api_client import get, post


@solara.component
def Page() -> None:
    start = solara.use_reactive("2024-01-01T00:00:00")
    end = solara.use_reactive("2024-01-01T01:00:00")
    mode = solara.use_reactive("manifest")
    tickers = solara.use_reactive("AAPL,MSFT")
    manifest: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    ingest_task = solara.use_reactive("")
    mentions: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    error = solara.use_reactive("")

    def fetch_manifest() -> None:
        try:
            payload = get(
                "/gdelt/manifest",
                params={"start": start.value, "end": end.value},
            )
            manifest.set(payload or {})
            error.set("")
        except Exception as exc:  # pragma: no cover
            manifest.set({})
            error.set(str(exc))

    def submit_ingest() -> None:
        try:
            ticker_list = [t.strip() for t in tickers.value.split(",") if t.strip()]
            body: dict[str, Any] = {
                "start": start.value,
                "end": end.value,
                "mode": mode.value,
            }
            if ticker_list:
                body["tickers"] = ticker_list
            r = post("/gdelt/ingest", json=body)
            ingest_task.set(str(r.get("task_id", "")))
            error.set("")
        except Exception as exc:  # pragma: no cover
            error.set(str(exc))

    def load_mentions(symbol: str | None = None) -> None:
        try:
            params: dict[str, Any] = {"limit": 100}
            if symbol:
                params["ticker"] = symbol
            payload = get("/gdelt/mentions", params=params)
            mentions.set(list(payload or []))
            error.set("")
        except Exception as exc:  # pragma: no cover
            mentions.set([])
            error.set(str(exc))

    with solara.Column(gap="12px", style={"padding": "16px", "max-width": "1200px"}):
        solara.Markdown("# GDelt GKG 2.0 Explorer")
        solara.Markdown(
            "Inspect the 15-minute manifest, ingest a window, or query "
            "BigQuery for ad-hoc cross-company patterns. Requires the "
            "`[gdelt]` extra; BigQuery federation needs `[gdelt-bq]`."
        )
        with solara.Row():
            solara.InputText(label="Start (ISO)", value=start)
            solara.InputText(label="End (ISO)", value=end)
            solara.Select(
                label="Mode",
                value=mode,
                values=["manifest", "bigquery", "hybrid"],
            )
        with solara.Row():
            solara.InputText(label="Ticker filter (comma-separated)", value=tickers)
            solara.Button("Fetch manifest", on_click=fetch_manifest)
            solara.Button("Ingest window", on_click=submit_ingest, color="primary")
            solara.Button("Recent mentions", on_click=lambda: load_mentions())

        if error.value:
            solara.Error(error.value)
        if ingest_task.value:
            solara.Info(f"Ingest task queued: {ingest_task.value}")

        if manifest.value:
            solara.Markdown(
                f"## Manifest slice — {manifest.value.get('count', 0)} files, "
                f"{manifest.value.get('total_bytes', 0):,} bytes"
            )
            entries = manifest.value.get("entries", [])
            if entries:
                solara.DataFrame(pd.DataFrame(entries))

        if mentions.value:
            solara.Markdown("## Mentions")
            solara.DataFrame(pd.DataFrame(mentions.value))
