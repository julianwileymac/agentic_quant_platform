"""Rich YAML editor with validate + save + reset + diff.

Factors out the inline ``solara.InputTextArea`` / ``yaml.safe_load`` dance
from Strategy Development, Backtest Lab, ML Training, and RL Dashboard. Adds
a small "validate now" action that surfaces parse errors inline instead of
the current pattern of erroring only on submission.
"""
from __future__ import annotations

import difflib
from collections.abc import Callable
from typing import Any

import solara
import yaml


@solara.component
def YamlEditor(
    value: solara.Reactive[str] | str,
    *,
    label: str = "YAML",
    rows: int = 20,
    on_save: Callable[[str], None] | None = None,
    on_reset: Callable[[], None] | None = None,
    on_submit: Callable[[dict[str, Any]], None] | None = None,
    diff_against: str | None = None,
    show_preview: bool = True,
) -> None:
    reactive = _as_reactive(value)
    status = solara.use_reactive("")  # "ok" | "error" | ""
    parsed: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    message = solara.use_reactive("")

    def _validate() -> None:
        text = reactive.value or ""
        try:
            doc = yaml.safe_load(text) or {}
            if not isinstance(doc, dict):
                raise ValueError("top-level must be a mapping")
            parsed.set(doc)
            status.set("ok")
            message.set(f"valid — {_summarise(doc)}")
        except Exception as exc:  # noqa: BLE001
            parsed.set({})
            status.set("error")
            message.set(str(exc))

    solara.use_effect(_validate, [reactive.value])

    tone_color = {
        "ok": ("#064e3b", "#bbf7d0"),
        "error": ("#7f1d1d", "#fecaca"),
        "": ("#334155", "#cbd5e1"),
    }[status.value]

    with solara.Column(gap="6px"):
        solara.InputTextArea(label, value=reactive, rows=rows)
        if message.value:
            solara.Markdown(
                f"<div style='background:{tone_color[0]};color:{tone_color[1]};"
                f"padding:6px 10px;border-radius:6px;font-size:12px'>"
                f"{message.value}</div>"
            )
        with solara.Row(gap="6px"):
            solara.Button("Validate", on_click=_validate, outlined=True)
            if on_save is not None:
                solara.Button(
                    "Save",
                    on_click=lambda: on_save(reactive.value),
                    color="primary",
                    disabled=status.value == "error",
                )
            if on_submit is not None:
                solara.Button(
                    "Submit",
                    on_click=lambda: on_submit(parsed.value),
                    color="warning",
                    disabled=status.value == "error",
                )
            if on_reset is not None:
                solara.Button("Reset", on_click=on_reset, outlined=True)

        if diff_against is not None:
            _render_diff(diff_against, reactive.value)
        if show_preview and parsed.value:
            with solara.Details(summary="Parsed preview"):
                solara.Markdown(
                    f"```yaml\n{yaml.safe_dump(parsed.value, sort_keys=False)}\n```"
                )


def _as_reactive(value: solara.Reactive[str] | str) -> solara.Reactive[str]:
    if isinstance(value, solara.Reactive):
        return value
    return solara.use_reactive(str(value or ""))


def _render_diff(base: str, current: str) -> None:
    if base == current:
        solara.Markdown("_No changes relative to reference._")
        return
    diff = "\n".join(
        difflib.unified_diff(
            (base or "").splitlines(),
            (current or "").splitlines(),
            fromfile="base",
            tofile="current",
            lineterm="",
        )
    )
    with solara.Details(summary="Diff vs. reference"):
        solara.Markdown(f"```diff\n{diff}\n```")


def _summarise(doc: dict[str, Any]) -> str:
    keys = list(doc.keys())[:4]
    more = f" +{len(doc) - len(keys)}" if len(doc) > len(keys) else ""
    return ", ".join(keys) + more
