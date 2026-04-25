"""Sources Explorer — live view of every registered data source.

Calls the ``/sources`` router (added as part of the data-plane
expansion) to list every row in the ``data_sources`` registry, probe
adapters for reachability, and toggle enabled/disabled without touching
the DB directly.
"""
from __future__ import annotations

from typing import Any

import solara

from aqp.ui.api_client import get, post


@solara.component
def Page() -> None:
    rows: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    probe_results: solara.Reactive[dict[str, dict[str, Any]]] = solara.use_reactive({})
    error_message = solara.use_reactive("")

    def refresh() -> None:
        try:
            rows.set(list(get("/sources") or []))
            error_message.set("")
        except Exception as exc:  # pragma: no cover - UI path
            rows.set([])
            error_message.set(str(exc))

    def run_probe(name: str) -> None:
        try:
            result = get(f"/sources/{name}/probe")
            current = dict(probe_results.value)
            current[name] = result
            probe_results.set(current)
        except Exception as exc:
            current = dict(probe_results.value)
            current[name] = {"ok": False, "message": str(exc)}
            probe_results.set(current)

    def toggle(name: str, enabled: bool) -> None:
        try:
            import httpx

            from aqp.ui.api_client import api_url

            with httpx.Client(timeout=30.0) as client:
                r = client.patch(api_url(f"/sources/{name}"), json={"enabled": enabled})
                r.raise_for_status()
        except Exception as exc:
            error_message.set(str(exc))
            return
        refresh()

    solara.use_effect(refresh, [])

    with solara.Column(gap="12px", style={"padding": "16px", "max-width": "1200px"}):
        solara.Markdown("# Data Sources")
        solara.Markdown(
            "Every registered source, its configuration, and a live "
            "reachability probe. Managed via `data_sources` table + the "
            "`/sources` API."
        )
        solara.Markdown("Need to set API keys? Open the [Credentials](/credentials) page.")
        with solara.Row():
            solara.Button("Refresh", on_click=refresh)
        if error_message.value:
            solara.Error(error_message.value)

        if not rows.value:
            solara.Info("No data sources registered. Apply the 0007 migration.")
            return

        for row in rows.value:
            name = row.get("name", "")
            probe_result = probe_results.value.get(name)
            with solara.Card(style={"padding": "16px"}):
                with solara.Row(justify="space-between"):
                    solara.Markdown(
                        f"**{row.get('display_name', name)}** (`{name}`)"
                    )
                    enabled = bool(row.get("enabled"))
                    solara.Switch(
                        label="Enabled" if enabled else "Disabled",
                        value=enabled,
                        on_value=lambda v, n=name: toggle(n, v),
                    )
                solara.Markdown(
                    f"**Kind:** {row.get('kind', '')}  •  "
                    f"**Auth:** {row.get('auth_type', '')}  •  "
                    f"**Vendor:** {row.get('vendor', '—')}"
                )
                if row.get("base_url"):
                    solara.Markdown(f"**Endpoint:** `{row['base_url']}`")
                if row.get("credentials_ref"):
                    solara.Markdown(
                        f"**Credential env var:** `{row['credentials_ref']}`"
                    )
                if row.get("capabilities"):
                    solara.Markdown(
                        f"**Domains:** {', '.join(row['capabilities'].get('domains') or []) or '—'}"
                    )
                with solara.Row():
                    solara.Button("Probe", on_click=lambda n=name: run_probe(n))
                if probe_result:
                    colour = "green" if probe_result.get("ok") else "red"
                    solara.Markdown(
                        f"<span style='color:{colour}'>● {probe_result.get('message', '')}</span>"
                    )
