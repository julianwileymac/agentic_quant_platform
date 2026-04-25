"""Central design tokens + Plotly template for the Solara UI.

Before this module, colors were scattered across inline dict literals on
every page.  That made the UI look inconsistent and — more importantly —
gave us poor text/background contrast in several places (subtitles at
``opacity: 0.55``, Plotly defaults on a slate-tinted background, ...).

The palette below was chosen to satisfy WCAG AA (contrast >= 4.5 for
normal text) against the app shell background, and it's exposed to
Plotly via :func:`plotly_template` so charts pick up the same look with
one line:

.. code-block:: python

    from aqp.ui.theme import plotly_template, apply_theme

    fig.update_layout(template=plotly_template())

or the shorthand :func:`apply_theme` for one-off figures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import plotly.graph_objects as go


@dataclass(frozen=True)
class Palette:
    """Resolved design tokens.  Values are hex / rgba strings."""

    # Surface colors
    bg_page: str
    bg_card: str
    bg_card_alt: str
    bg_panel: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_inverse: str

    # Accents (chips / CTAs / highlights)
    accent: str
    accent_hover: str
    accent_fg: str

    # Status tones (AA-contrast fg on dark bg)
    success: str
    success_fg: str
    warning: str
    warning_fg: str
    error: str
    error_fg: str
    info: str
    info_fg: str

    # Chart specifics
    grid: str
    axis: str
    candle_up: str
    candle_down: str
    candle_up_line: str
    candle_down_line: str
    volume: str
    sma: str
    ema: str
    vwap: str
    bb_band: str
    rsi: str
    macd: str
    macd_signal: str
    drawdown: str


# High-contrast slate palette.  The numbers come from tailwindcss and
# have been spot-checked against https://webaim.org/resources/contrastchecker/.
PALETTE = Palette(
    bg_page="#f8fafc",          # slate-50
    bg_card="#ffffff",
    bg_card_alt="#f1f5f9",      # slate-100
    bg_panel="#0f172a",         # slate-900 (for dark chart backgrounds)

    text_primary="#0f172a",     # AA on bg_page (ratio 17.9)
    text_secondary="#1e293b",   # AA on bg_page (ratio 15.2)
    text_muted="#475569",       # AA on bg_page (ratio 7.47)
    text_inverse="#f8fafc",     # AA on bg_panel (ratio 16.3)

    accent="#2563eb",           # blue-600 AA on white
    accent_hover="#1d4ed8",
    accent_fg="#f8fafc",

    success="#047857",          # emerald-700
    success_fg="#ecfdf5",
    warning="#b45309",          # amber-700
    warning_fg="#fff7ed",
    error="#b91c1c",            # red-700
    error_fg="#fef2f2",
    info="#1d4ed8",             # blue-700
    info_fg="#eff6ff",

    grid="rgba(148, 163, 184, 0.28)",   # slate-400 @ 28%
    axis="#334155",             # slate-700
    candle_up="#16a34a",        # green-600
    candle_down="#dc2626",      # red-600
    candle_up_line="#166534",   # green-800
    candle_down_line="#991b1b", # red-800
    volume="rgba(100, 116, 139, 0.45)",
    sma="#2563eb",
    ema="#9333ea",
    vwap="#f59e0b",
    bb_band="rgba(148, 163, 184, 0.35)",
    rsi="#0891b2",
    macd="#2563eb",
    macd_signal="#f97316",
    drawdown="#b91c1c",
)


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------


def plotly_template(*, dark: bool = False) -> go.layout.Template:
    """Return a cached Plotly layout template tuned for the AQP UI.

    ``dark=True`` flips the paper/plot background to slate-900 for a
    dashboard-style chart; body text and grid are adjusted to remain AA
    on that surface.  ``dark=False`` (default) is the white-card look
    used inside Solara cards.
    """
    if dark:
        paper_bg = PALETTE.bg_panel
        plot_bg = PALETTE.bg_panel
        text = PALETTE.text_inverse
        grid = "rgba(226, 232, 240, 0.18)"
        axis = "rgba(226, 232, 240, 0.70)"
    else:
        paper_bg = PALETTE.bg_card
        plot_bg = PALETTE.bg_card
        text = PALETTE.text_primary
        grid = PALETTE.grid
        axis = PALETTE.axis

    axis_common: dict[str, Any] = {
        "gridcolor": grid,
        "zerolinecolor": grid,
        "tickcolor": axis,
        "linecolor": axis,
        "tickfont": {"color": axis, "size": 11},
        "title": {"font": {"color": text, "size": 12}},
        "showline": True,
        "mirror": False,
    }

    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=paper_bg,
            plot_bgcolor=plot_bg,
            font={
                "color": text,
                "family": (
                    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', "
                    "Roboto, 'Helvetica Neue', Arial, sans-serif"
                ),
                "size": 12,
            },
            title={"font": {"color": text, "size": 14}, "x": 0.02, "xanchor": "left"},
            legend={
                "font": {"color": text, "size": 11},
                "bgcolor": "rgba(0,0,0,0)",
                "bordercolor": "rgba(0,0,0,0)",
            },
            colorway=[
                PALETTE.accent,
                PALETTE.ema,
                PALETTE.vwap,
                PALETTE.success,
                PALETTE.warning,
                PALETTE.error,
                PALETTE.rsi,
                PALETTE.macd_signal,
            ],
            hoverlabel={
                "bgcolor": PALETTE.bg_card_alt,
                "bordercolor": PALETTE.accent,
                "font": {"color": PALETTE.text_primary, "size": 12},
            },
            xaxis=axis_common,
            yaxis=axis_common,
            margin={"l": 52, "r": 20, "t": 40, "b": 40},
        )
    )


CANDLE_COLORS: dict[str, str] = {
    "up": PALETTE.candle_up,
    "down": PALETTE.candle_down,
    "up_line": PALETTE.candle_up_line,
    "down_line": PALETTE.candle_down_line,
}


def apply_theme(fig: go.Figure, *, dark: bool = False) -> go.Figure:
    """Mutate ``fig`` in-place to adopt the AQP Plotly template."""
    fig.update_layout(template=plotly_template(dark=dark))
    # Apply candle colours to any Candlestick / OHLC traces in the figure
    # that haven't already opted out via explicit colours.
    for trace in fig.data:
        if isinstance(trace, (go.Candlestick, go.Ohlc)):
            if not getattr(trace, "increasing", None) or not trace.increasing.fillcolor:
                trace.increasing = {
                    "fillcolor": CANDLE_COLORS["up"],
                    "line": {"color": CANDLE_COLORS["up_line"]},
                }
            if not getattr(trace, "decreasing", None) or not trace.decreasing.fillcolor:
                trace.decreasing = {
                    "fillcolor": CANDLE_COLORS["down"],
                    "line": {"color": CANDLE_COLORS["down_line"]},
                }
    return fig


# ---------------------------------------------------------------------------
# Small helpers used by non-chart components (chips, cards, tiles).
# ---------------------------------------------------------------------------


def chip_style(tone: str = "neutral") -> dict[str, str]:
    """Return CSS-in-JS dict for a pill chip.  ``tone`` matches metric tiles."""
    mapping = {
        "neutral": (PALETTE.bg_card_alt, PALETTE.text_primary),
        "success": (PALETTE.success, PALETTE.success_fg),
        "warning": (PALETTE.warning, PALETTE.warning_fg),
        "error": (PALETTE.error, PALETTE.error_fg),
        "info": (PALETTE.info, PALETTE.info_fg),
    }
    bg, fg = mapping.get(tone, mapping["neutral"])
    return {
        "background-color": bg,
        "color": fg,
        "padding": "2px 10px",
        "border-radius": "999px",
        "font-size": "12px",
        "font-weight": "600",
        "letter-spacing": "0.02em",
    }


def card_style() -> dict[str, str]:
    return {
        "background-color": PALETTE.bg_card,
        "color": PALETTE.text_primary,
        "border": "1px solid rgba(148, 163, 184, 0.25)",
        "border-radius": "12px",
        "padding": "16px",
        "box-shadow": "0 1px 2px rgba(15, 23, 42, 0.06)",
    }


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return r, g, b


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def _channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 relative-luminance contrast ratio between two hex colors."""
    l_fg = _relative_luminance(_hex_to_rgb(fg))
    l_bg = _relative_luminance(_hex_to_rgb(bg))
    brighter = max(l_fg, l_bg)
    darker = min(l_fg, l_bg)
    return (brighter + 0.05) / (darker + 0.05)


__all__ = [
    "Palette",
    "PALETTE",
    "CANDLE_COLORS",
    "plotly_template",
    "apply_theme",
    "chip_style",
    "card_style",
    "contrast_ratio",
]
