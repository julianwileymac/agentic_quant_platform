"""Credential manager for source probes and ingestion adapters.

The page lists discovered credential env-vars (from ``/sources`` metadata),
lets users edit them in one place, and persists updates via
``PUT /sources/credentials``. The API route applies values to both ``.env``
and the running process for immediate probe retries.
"""
from __future__ import annotations

from typing import Any

import solara

from aqp.ui.api_client import get, put


@solara.component
def Page() -> None:
    entries: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    values: solara.Reactive[dict[str, str]] = solara.use_reactive({})
    env_file = solara.use_reactive(".env")
    error_message = solara.use_reactive("")
    status_message = solara.use_reactive("")

    def refresh() -> None:
        try:
            payload = get("/sources/credentials") or {}
            rows = list(payload.get("credentials") or [])
            entries.set(rows)
            env_file.set(str(payload.get("env_file") or ".env"))
            values.set(
                {
                    str(row.get("key")): str(row.get("value") or "")
                    for row in rows
                    if row.get("key")
                }
            )
            error_message.set("")
        except Exception as exc:  # pragma: no cover - UI path
            error_message.set(str(exc))

    def set_value(key: str, value: str) -> None:
        current = dict(values.value)
        current[key] = value
        values.set(current)

    def save() -> None:
        try:
            payload = put("/sources/credentials", json={"values": dict(values.value)}) or {}
            updated = list(payload.get("updated") or [])
            status_message.set(f"Saved {len(updated)} credential value(s).")
            error_message.set("")
            refresh()
        except Exception as exc:  # pragma: no cover - UI path
            error_message.set(str(exc))

    solara.use_effect(refresh, [])

    with solara.Column(gap="12px", style={"padding": "16px", "max-width": "1100px"}):
        solara.Markdown("# Credentials")
        solara.Markdown(
            "Set provider credentials in one place. Values are written to "
            "the API `.env` and applied to the running API process for live "
            "probe retries."
        )
        solara.Markdown(f"**Environment file:** `{env_file.value}`")
        with solara.Row():
            solara.Button("Reload", on_click=refresh, outlined=True)
            solara.Button("Save credentials", on_click=save, color="primary")

        if status_message.value:
            solara.Success(status_message.value)
        if error_message.value:
            solara.Error(error_message.value)

        if not entries.value:
            solara.Info("No credential keys discovered yet. Check source metadata.")
            return

        for row in entries.value:
            key = str(row.get("key") or "")
            used_by = list(row.get("used_by") or [])
            value = values.value.get(key, "")
            configured = bool(str(value).strip())
            with solara.Card(style={"padding": "12px"}):
                solara.Markdown(f"**{key}**")
                if used_by:
                    solara.Markdown(f"**Used by:** {', '.join(sorted(used_by))}")
                solara.Markdown(
                    f"**Status:** {'configured' if configured else 'missing'}"
                )
                solara.InputText(
                    label="Value",
                    value=value,
                    on_value=lambda v, k=key: set_value(k, v),
                )
