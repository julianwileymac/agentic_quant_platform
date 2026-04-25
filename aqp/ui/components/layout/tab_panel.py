"""Lightweight tabbed container used by Workbench pages.

Solara ships with ``solara.lab.Tabs`` but the API is in flux; this shim is
version-agnostic and uses a styled button bar + swap panel. Each page
passes a list of :class:`TabSpec` and a callable that renders that tab's
content on activation.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import solara


@dataclass
class TabSpec:
    key: str
    label: str
    render: Callable[[], None]
    icon: str | None = None
    badge: str | int | None = None


@solara.component
def TabPanel(
    tabs: list[TabSpec],
    *,
    active_key: str | None = None,
    on_change: Callable[[str], None] | None = None,
) -> None:
    default_active = active_key or (tabs[0].key if tabs else "")
    active = solara.use_reactive(default_active)
    if not tabs:
        return

    def _activate(key: str) -> None:
        active.set(key)
        if on_change is not None:
            on_change(key)

    with solara.Column(gap="12px", style={"flex": "1", "min-width": "0"}):
        with solara.Row(
            gap="4px",
            style={
                "border-bottom": "1px solid rgba(148, 163, 184, 0.25)",
                "padding-bottom": "0",
                "flex-wrap": "wrap",
            },
        ):
            for spec in tabs:
                _render_tab_button(spec, active.value == spec.key, _activate)

        active_spec = next((s for s in tabs if s.key == active.value), tabs[0])
        with solara.Div(
            style={
                "padding": "6px 2px 2px 2px",
                "flex": "1",
                "min-width": "0",
            }
        ):
            active_spec.render()


def _render_tab_button(
    spec: TabSpec, is_active: bool, on_click: Callable[[str], None]
) -> None:
    label = spec.label
    if spec.icon:
        label = f"{spec.icon} {label}"
    if spec.badge is not None:
        label += f"  ({spec.badge})"
    solara.Button(
        label=label,
        on_click=lambda: on_click(spec.key),
        text=not is_active,
        color="primary" if is_active else None,
        classes=["aqp-tab", "aqp-tab--active" if is_active else "aqp-tab--idle"],
        style={
            "border-radius": "8px 8px 0 0",
            "border-bottom": "3px solid #38bdf8" if is_active else "3px solid transparent",
            "font-weight": "600" if is_active else "500",
            "padding": "8px 14px",
            "text-transform": "none",
            "letter-spacing": "0.01em",
        },
    )
