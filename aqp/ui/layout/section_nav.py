"""Grouped sidebar navigation.

Reads the currently registered :class:`solara.Route` list, groups routes
by the ``section`` key on each route's ``data`` payload, and renders a
section header + list of links per group. Used inside
:func:`aqp.ui.layout.AppShell`.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import solara

from aqp.ui.theme import PALETTE

if TYPE_CHECKING:  # pragma: no cover
    from aqp.ui.layout.app_shell import NavSectionSpec


@solara.component
def SectionNav(sections: Iterable[Any]) -> None:
    _, all_routes = solara.use_route()
    router = solara.use_router()
    active_path = router.path

    grouped = _group_routes(list(all_routes), sections)
    leftover = _unassigned(list(all_routes), grouped)
    if leftover:
        grouped["__misc__"] = leftover

    with solara.Column(
        gap="10px",
        style={
            "padding": "12px 8px",
            "min-width": "240px",
            "height": "100%",
            "overflow-y": "auto",
        },
    ):
        for section in sections:
            routes = grouped.get(section.id, [])
            if not routes:
                continue
            _render_section(section, routes, active_path)

        if leftover:
            _render_section_raw("Other", leftover, active_path, icon="mdi-folder-outline")


def _render_section(section: Any, routes: list[Any], active_path: str) -> None:
    """Render a section header + its clickable children."""
    _render_section_raw(
        label=section.label,
        routes=routes,
        active_path=active_path,
        icon=section.icon,
    )


def _render_section_raw(
    label: str,
    routes: list[Any],
    active_path: str,
    *,
    icon: str = "mdi-folder",
) -> None:
    with solara.Column(gap="2px"):
        solara.Markdown(
            f"<div style='font-size:10px;text-transform:uppercase;letter-spacing:0.1em;"
            f"color:{PALETTE.text_muted};padding:0 8px;margin-top:6px;font-weight:700'>{label}</div>"
        )
        for route in routes:
            _render_link(route, active_path)


def _render_link(route: Any, active_path: str) -> None:
    path = route.path or "/"
    label = route.label or path
    icon = _extract_icon(route)
    href = _href(path)
    is_active = _is_active(path, active_path)

    # Active link: solid slate background + bright text.
    # Idle link: high-contrast text directly on the page background.
    bg = PALETTE.bg_panel if is_active else "transparent"
    fg = PALETTE.text_inverse if is_active else PALETTE.text_secondary
    accent = PALETTE.accent if is_active else "transparent"

    solara.HTML(
        tag="a",
        unsafe_innerHTML=(
            f"<span style='font-size:13px;font-weight:{600 if is_active else 500};'>"
            f"{icon}&nbsp;&nbsp;{label}</span>"
        ),
        attributes={
            "href": href,
            "style": (
                f"display:block;padding:7px 12px;border-radius:8px;text-decoration:none;"
                f"background:{bg};color:{fg};border-left:3px solid {accent};"
                "transition:background 0.15s ease"
            ),
        },
    )


def _group_routes(
    routes: list[Any], sections: Iterable[Any]
) -> dict[str, list[Any]]:
    section_ids = {s.id for s in sections}
    grouped: dict[str, list[Any]] = {s.id: [] for s in sections}
    for route in routes:
        section = _route_section(route)
        if section and section in section_ids:
            grouped[section].append(route)
    return grouped


def _unassigned(routes: list[Any], grouped: dict[str, list[Any]]) -> list[Any]:
    claimed = {id(r) for rs in grouped.values() for r in rs}
    return [r for r in routes if id(r) not in claimed]


def _route_section(route: Any) -> str | None:
    data = getattr(route, "data", None) or {}
    if isinstance(data, dict):
        return data.get("section")
    return None


def _extract_icon(route: Any) -> str:
    """Lightweight icon rendering using MDI-style CSS classes when present.

    Because Solara ships Vuetify + MDI we could mount real icons, but the
    HTML sidebar we render here uses raw markup, so we fall back to a
    tiny unicode glyph for now.
    """
    data = getattr(route, "data", None) or {}
    if isinstance(data, dict):
        glyph = data.get("glyph")
        if glyph:
            return str(glyph)
    return "•"


def _href(path: str) -> str:
    if path == "/":
        return "/"
    return "/" + path.lstrip("/")


def _is_active(path: str, active_path: str) -> bool:
    normalised = "/" + (path or "").strip("/")
    current = "/" + (active_path or "").strip("/")
    if normalised == "/":
        return current in {"/", ""}
    return current == normalised or current.startswith(normalised + "/")
