"""AppShell — top bar + grouped sidebar + page outlet.

Solara renders a default sidebar from the ``routes`` list. We supersede it
by defining a ``Layout`` component in :mod:`aqp.ui.app` that delegates to
:func:`AppShell`. The shell itself:

- declares the section taxonomy (:data:`NAV_SECTIONS`);
- fills Solara's ``Sidebar`` portal with our custom :class:`SectionNav`
  instead of the default list;
- fills the ``AppBar`` with status pills for env / kill-switch / queue
  depth;
- renders the passed-in children in the content slot.

Each :class:`solara.Route` in ``aqp.ui.app`` carries a
``data={"section": "research", ...}`` key so :class:`SectionNav` knows
which group a given page belongs to.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import solara

from aqp.ui.layout.section_nav import SectionNav
from aqp.ui.theme import PALETTE


@dataclass
class NavSectionSpec:
    """Describes one group of pages in the sidebar.

    ``id`` is the section key used on each :class:`solara.Route.data` dict.
    ``label`` + ``icon`` control the section header in the sidebar.
    """

    id: str
    label: str
    icon: str = "mdi-apps"
    tone: str = "neutral"  # matches MetricTile tones — purely visual


NAV_SECTIONS: list[NavSectionSpec] = [
    NavSectionSpec(id="home", label="Dashboard", icon="mdi-view-dashboard-variant", tone="info"),
    NavSectionSpec(id="research", label="Research", icon="mdi-telescope", tone="info"),
    NavSectionSpec(id="data", label="Data", icon="mdi-database-outline", tone="success"),
    NavSectionSpec(id="lab", label="Lab", icon="mdi-flask-outline", tone="warning"),
    NavSectionSpec(id="execution", label="Execution", icon="mdi-rocket-launch-outline", tone="error"),
    NavSectionSpec(id="monitor", label="Monitor", icon="mdi-monitor-dashboard", tone="neutral"),
]


@solara.component
def AppShell(children: Any) -> None:
    """Wrap ``children`` in our grouped-sidebar + top-bar shell.

    Callable from the module-level ``Layout(children)`` Solara discovers in
    :mod:`aqp.ui.app` (see that file's bottom for the hand-off).
    """
    solara.Title("Agentic Quant Platform")

    with solara.AppLayout(sidebar_open=True, navigation=False):
        with solara.AppBarTitle():
            _render_title_bar()
        with solara.AppBar():
            _render_status_chips()
        with solara.Sidebar():
            SectionNav(sections=NAV_SECTIONS)

        with solara.Column(
            gap="0",
            style={
                "padding": "0",
                "background": PALETTE.bg_page,
                "color": PALETTE.text_primary,
                "min-height": "100%",
            },
        ):
            # ``children`` is a list of Reacton elements passed by Solara's
            # multipage router; dropping them in-place is the idiomatic hand
            # off to the active page component.
            solara.Div(children=children)


def _render_title_bar() -> None:
    with solara.Row(gap="8px", style={"align-items": "center"}):
        solara.Text("AQP")
        solara.Markdown(
            "<span style='font-size:12px;opacity:0.92;letter-spacing:0.08em;"
            "text-transform:uppercase;margin-left:4px'>agentic quant platform</span>"
        )


def _render_status_chips() -> None:
    """Live environment / kill-switch / queue pills.

    Pure network-side: each pill fetches its data via ``use_api`` so a dead
    API does not break the shell — pills fall back to a muted dash.
    """
    from aqp.ui.components.data.use_api import use_api

    ks = use_api("/portfolio/kill_switch", default={}, interval=15.0)
    health = use_api("/health", default={}, interval=30.0)

    with solara.Row(gap="8px", style={"align-items": "center"}):
        _env_chip(health.value or {})
        _kill_switch_chip(ks.value or {})


def _env_chip(health: dict[str, Any]) -> None:
    ok = bool(health.get("ollama") and health.get("postgres") and health.get("redis"))
    bg = PALETTE.success if ok else PALETTE.error
    label = "ONLINE" if ok else "DEGRADED"
    services = []
    if health:
        services = [k for k in ("ollama", "postgres", "redis", "chromadb") if not health.get(k)]
    tooltip = "All services healthy" if ok else f"Missing: {', '.join(services) or 'unknown'}"
    _chip(label, bg, tooltip=tooltip)


def _kill_switch_chip(ks: dict[str, Any]) -> None:
    engaged = bool(ks.get("engaged"))
    bg = PALETTE.error if engaged else PALETTE.info
    label = "KILL" if engaged else "LIVE"
    tooltip = f"Kill switch: {ks.get('reason') or '-'}" if engaged else "Kill switch released"
    _chip(label, bg, tooltip=tooltip)


def _chip(label: str, bg: str, *, tooltip: str = "") -> None:
    solara.HTML(
        tag="span",
        unsafe_innerHTML=label,
        attributes={
            "title": tooltip,
            "style": (
                f"background:{bg};color:{PALETTE.text_inverse};padding:3px 10px;"
                "border-radius:999px;font-size:11px;font-weight:700;"
                "letter-spacing:0.05em"
            ),
        },
    )
