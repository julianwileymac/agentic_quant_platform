"""Inline iframe embed for a Dash sub-app.

Used anywhere dense Dash-only features (live strategy monitor, optimizer
heatmap grid) need to sit inside a Solara page. The slug maps to the URL
prefix the app is mounted under in :func:`aqp.api.main._mount_dash`.
"""
from __future__ import annotations

import os

import solara

_API_URL = os.environ.get("AQP_API_URL", "http://localhost:8000").rstrip("/")


@solara.component
def DashEmbed(
    slug: str = "",
    *,
    dash_url: str | None = None,
    height: int = 720,
    title: str | None = None,
    caption: str | None = None,
) -> None:
    """Embed a Dash app at ``/dash/<slug>/`` (or ``dash_url`` if given)."""
    url = dash_url or f"{_API_URL}/dash/{slug.strip('/')}/" if slug else f"{_API_URL}/dash/"
    override = os.environ.get("AQP_DASH_URL")
    if override and not dash_url:
        url = override.rstrip("/") + ("/" + slug.strip("/") + "/" if slug else "/")

    with solara.Column(gap="8px"):
        if title:
            solara.Markdown(f"### {title}")
        if caption:
            solara.Markdown(caption)
        solara.HTML(
            tag="iframe",
            attributes={
                "src": url,
                "width": "100%",
                "height": str(int(height)),
                "frameborder": "0",
                "style": "border:1px solid rgba(148, 163, 184, 0.25); border-radius: 12px;",
            },
        )
