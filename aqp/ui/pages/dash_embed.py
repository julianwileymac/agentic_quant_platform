"""Embedded Dash dashboard for a strategy live-monitor.

By default we point the iframe at ``<AQP_API_URL>/dash/`` so the Dash app
runs inside FastAPI on the same port. When users prefer the legacy
standalone Dash server, set ``AQP_DASH_URL=http://localhost:8050``.
"""
from __future__ import annotations

import os

import solara

_API_URL = os.environ.get("AQP_API_URL", "http://localhost:8000").rstrip("/")
_DASH_URL = os.environ.get("AQP_DASH_URL", f"{_API_URL}/dash/")


@solara.component
def Page() -> None:
    with solara.Column(gap="12px", style={"padding": "16px"}):
        solara.Markdown("# Strategy Monitor (Dash)")
        solara.Markdown(
            f"Embedded Dash app served at `{_DASH_URL}`. "
            "By default this is mounted inside FastAPI, so the whole platform "
            "runs on a single port. Override with `AQP_DASH_URL` if you run "
            "the standalone Dash server (`python -m aqp.ui.dash_app`)."
        )
        solara.HTML(
            tag="iframe",
            attributes={
                "src": _DASH_URL,
                "width": "100%",
                "height": "720",
                "frameborder": "0",
            },
        )
