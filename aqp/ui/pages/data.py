"""Data Explorer — browse the Parquet lake, search metadata, and load local files.

Sections:
1. **Parquet catalog** — a summary of every symbol in the local lake.
2. **Load local files** — point AQP at CSV or Parquet files on a mounted drive
   (``POST /data/load``). Normalises them into the canonical tidy schema and
   writes into the Parquet lake so the DuckDB view + backtest pipeline see them.
3. **Ingest market bars** — one-click ingest of the active/default universe.
4. **Managed universe snapshot** — sync and browse the Alpha Vantage universe.
5. **Semantic search** — query the ChromaDB metadata index.
"""
from __future__ import annotations

import json

import pandas as pd
import solara

from aqp.ui.api_client import get, post


@solara.component
def Page() -> None:
    query = solara.use_reactive("")
    results = solara.use_reactive([])
    catalog = solara.use_reactive([])
    ingest_source = solara.use_reactive("auto")
    ingest_task_id = solara.use_reactive("")

    # Local loader form state
    load_path = solara.use_reactive("")
    load_format = solara.use_reactive("csv")
    load_glob = solara.use_reactive("")
    load_tz = solara.use_reactive("")
    load_overwrite = solara.use_reactive(False)
    load_mapping = solara.use_reactive("")
    load_result = solara.use_reactive("")
    universe_query = solara.use_reactive("")
    universe_rows = solara.use_reactive([])
    universe_source = solara.use_reactive("config")
    universe_sync_state = solara.use_reactive("active")
    universe_sync_limit = solara.use_reactive("500")
    universe_sync_include_otc = solara.use_reactive(False)
    universe_task_id = solara.use_reactive("")

    def refresh() -> None:
        try:
            catalog.set(get("/data/describe") or [])
        except Exception as e:
            catalog.set([{"error": str(e)}])

    def refresh_universe() -> None:
        params: dict[str, str] = {}
        if universe_query.value.strip():
            params["query"] = universe_query.value.strip()
        try:
            payload = get("/data/universe", params=params)
            universe_rows.set(payload.get("items", []))
            universe_source.set(str(payload.get("source") or "config"))
        except Exception as exc:
            universe_rows.set([{"error": str(exc)}])
            universe_source.set("error")

    def search() -> None:
        if not query.value.strip():
            return
        try:
            r = post("/data/search", json={"query": query.value, "k": 8})
            results.set(r.get("results", []))
        except Exception as e:
            results.set([{"error": str(e)}])

    def ingest() -> None:
        try:
            r = post("/data/ingest", json={"source": ingest_source.value})
            ingest_task_id.set(str(r.get("task_id") or ""))
            solara.Info(f"Ingest kicked off: {r.get('task_id')}")
        except Exception as e:
            solara.Error(f"{e}")

    def sync_universe() -> None:
        body: dict[str, object] = {
            "state": universe_sync_state.value,
            "include_otc": bool(universe_sync_include_otc.value),
        }
        raw_limit = universe_sync_limit.value.strip()
        if raw_limit:
            try:
                body["limit"] = int(raw_limit)
            except ValueError:
                solara.Error("Universe sync limit must be a number.")
                return
        if universe_query.value.strip():
            body["query"] = universe_query.value.strip()
        try:
            resp = post("/data/universe/sync", json=body)
            universe_task_id.set(str(resp.get("task_id") or ""))
            solara.Info(f"Universe sync kicked off: {resp.get('task_id')}")
        except Exception as exc:
            solara.Error(str(exc))

    def reindex() -> None:
        try:
            r = post("/data/index", json=None)
            solara.Info(f"Index kicked off: {r.get('task_id')}")
        except Exception as e:
            solara.Error(f"{e}")

    def load_local() -> None:
        path = load_path.value.strip()
        if not path:
            solara.Warning("Enter a path first.")
            return
        body: dict = {
            "source_dir": path,
            "format": load_format.value,
            "overwrite": bool(load_overwrite.value),
        }
        if load_glob.value.strip():
            body["glob"] = load_glob.value.strip()
        if load_tz.value.strip():
            body["tz"] = load_tz.value.strip()
        if load_mapping.value.strip():
            try:
                body["column_map"] = json.loads(load_mapping.value)
            except json.JSONDecodeError as exc:
                solara.Error(f"column_map must be a JSON object: {exc}")
                return
        try:
            r = post("/data/load", json=body)
            load_result.set(json.dumps(r, indent=2, default=str))
            solara.Info(f"Load task queued: {r.get('task_id')}")
        except Exception as exc:
            load_result.set(str(exc))
            solara.Error(str(exc))

    def _refresh_all() -> None:
        refresh()
        refresh_universe()

    solara.use_effect(_refresh_all, [])

    with solara.Column(gap="12px", style={"padding": "16px", "max-width": "1200px"}):
        solara.Markdown("# Data Explorer")
        with solara.Row():
            solara.Button("Refresh catalog", on_click=refresh)
            solara.Select(
                label="Ingest source",
                value=ingest_source,
                values=["auto", "alpha_vantage", "yfinance"],
            )
            solara.Button("Ingest default universe", on_click=ingest, color="primary")
            solara.Button("Reindex ChromaDB", on_click=reindex)
        if ingest_task_id.value:
            solara.Markdown(f"Ingest task: `{ingest_task_id.value}`")

        solara.Markdown("## Parquet catalog")
        if catalog.value:
            df = pd.DataFrame(catalog.value)
            solara.DataFrame(df, items_per_page=20)
        else:
            solara.Markdown("_No data yet — run `aqp data ingest` or use the Load panel below._")

        # -----------------------------------------------------------------
        # Local-drive loader
        # -----------------------------------------------------------------
        with solara.Card("Load local files"):
            solara.Markdown(
                "Load CSV or Parquet files from a directory on the host "
                "(or any mounted drive) into the canonical tidy schema "
                "(`timestamp, vt_symbol, open, high, low, close, volume`). "
                "Files are merged into the Parquet lake so every other page "
                "picks them up automatically.\n\n"
                "_If your files don't already use the canonical column names, "
                "provide a JSON column mapping such as_ "
                "`{\"Date\":\"timestamp\",\"Adj Close\":\"close\"}`."
            )
            solara.InputText("Source directory (absolute path)", value=load_path)
            with solara.Row():
                solara.Select(label="Format", value=load_format, values=["csv", "parquet"])
                solara.InputText("Glob pattern (default *.csv or *.parquet)", value=load_glob)
                solara.InputText("Timezone (e.g. US/Eastern)", value=load_tz)
            solara.Checkbox(label="Overwrite existing files in the lake", value=load_overwrite)
            solara.InputTextArea(
                "Column mapping (JSON, optional)",
                value=load_mapping,
                rows=3,
            )
            solara.Button("Load into lake", on_click=load_local, color="primary")
            if load_result.value:
                solara.Markdown(f"```json\n{load_result.value}\n```")

        with solara.Card("Managed universe snapshot"):
            solara.Markdown(
                "Sync and browse the managed symbol universe. The backend pulls "
                "Alpha Vantage listing status data into the local Instrument catalog "
                "and falls back to `AQP_DEFAULT_UNIVERSE` when no snapshot exists."
            )
            with solara.Row():
                solara.Select(
                    label="Listing state",
                    value=universe_sync_state,
                    values=["active", "delisted"],
                )
                solara.InputText("Sync limit", value=universe_sync_limit)
                solara.Checkbox(label="Include OTC symbols", value=universe_sync_include_otc)
            with solara.Row():
                solara.InputText("Search ticker/name", value=universe_query)
                solara.Button("Refresh universe", on_click=refresh_universe)
                solara.Button("Sync Universe Snapshot (Alpha Vantage)", on_click=sync_universe, color="primary")
            solara.Markdown(f"Universe source: `{universe_source.value}`")
            if universe_task_id.value:
                solara.Markdown(f"Last sync task: `{universe_task_id.value}`")
            if universe_rows.value:
                solara.DataFrame(pd.DataFrame(universe_rows.value), items_per_page=15)

        # -----------------------------------------------------------------
        # Semantic search
        # -----------------------------------------------------------------
        solara.Markdown("## Semantic search")
        solara.InputText("Describe the data you need", value=query)
        solara.Button("Search", on_click=search)
        for h in results.value:
            meta = h.get("metadata", {}) if isinstance(h, dict) else {}
            solara.Markdown(
                f"- **{meta.get('vt_symbol', '?')}** — `{meta.get('path', '?')}` "
                f"({meta.get('rows', '?')} rows, {meta.get('first_ts', '?')}..{meta.get('last_ts', '?')})\n"
                f"  distance: {h.get('distance')}\n"
                f"  {h.get('document', '')}"
            )
