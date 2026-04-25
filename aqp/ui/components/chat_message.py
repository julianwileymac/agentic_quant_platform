"""Chat-bubble component with optional inline Plotly chart."""
from __future__ import annotations

import solara


@solara.component
def ChatBubble(role: str, content: str, chart_json: dict | None = None) -> None:
    is_user = role == "user"
    align = "flex-end" if is_user else "flex-start"
    bg = "#2563eb" if is_user else "#111827"
    fg = "#f8fafc"
    with solara.Row(style={"justify-content": align, "margin": "8px 0"}), solara.Column(
        style={
            "max-width": "75%",
            "background": bg,
            "color": fg,
            "padding": "10px 14px",
            "border-radius": "14px",
            "box-shadow": "0 1px 2px rgba(0,0,0,0.12)",
        }
    ):
        solara.Markdown(f"**{role.upper()}**\n\n{content}")
        if chart_json:
            try:
                import plotly.graph_objects as go

                fig = go.Figure(chart_json)
                solara.FigurePlotly(fig)
            except Exception as e:  # pragma: no cover
                solara.Warning(f"Could not render chart: {e}")
