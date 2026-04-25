"""Reusable page header component.

Every page that opts in gets the same title + subtitle + action-slot
layout, so the UI reads consistently across the 17 routes. Actions can be
arbitrary Solara elements — buttons, status chips, refresh icons, docs
links.
"""
from __future__ import annotations

from collections.abc import Callable

import solara

from aqp.ui.theme import PALETTE


@solara.component
def PageHeader(
    title: str,
    *,
    subtitle: str | None = None,
    icon: str | None = None,
    actions: Callable[[], None] | None = None,
    breadcrumb: list[str] | None = None,
) -> None:
    with solara.Column(
        gap="4px",
        style={
            "padding": "18px 20px 12px 20px",
            "background": (
                "linear-gradient(180deg, rgba(15, 23, 42, 0.05) 0%, transparent 100%)"
            ),
            "border-bottom": "1px solid rgba(148, 163, 184, 0.25)",
            "color": PALETTE.text_primary,
        },
    ):
        if breadcrumb:
            solara.Markdown(_format_breadcrumb(breadcrumb))
        with solara.Row(
            gap="12px",
            style={"align-items": "center", "justify-content": "space-between"},
        ):
            with solara.Row(gap="10px", style={"align-items": "center"}):
                if icon:
                    solara.Markdown(
                        f"<div style='font-size:22px'>{icon}</div>"
                    )
                solara.Markdown(
                    f"<h2 style='margin:0;font-size:22px;font-weight:700;color:{PALETTE.text_primary}'>{title}</h2>"
                )
            if actions is not None:
                with solara.Row(gap="6px", style={"align-items": "center"}):
                    actions()
        if subtitle:
            solara.Markdown(
                f"<div style='font-size:13px;color:{PALETTE.text_muted};max-width:960px'>{subtitle}</div>"
            )


def _format_breadcrumb(parts: list[str]) -> str:
    rendered = " / ".join(
        f"<span style='color:{PALETTE.text_muted}'>{p}</span>" for p in parts[:-1]
    )
    last = f"<span style='color:{PALETTE.text_secondary}'>{parts[-1]}</span>" if parts else ""
    sep = " / " if rendered and last else ""
    return (
        f"<div style='font-size:11px;text-transform:uppercase;letter-spacing:0.08em'>"
        f"{rendered}{sep}{last}</div>"
    )
