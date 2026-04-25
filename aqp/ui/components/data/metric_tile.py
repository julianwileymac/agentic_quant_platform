"""KPI tile used on Dashboard Home, Portfolio, Paper Runs, ML Model Detail.

A MetricTile is an OpenBB-terminal / Bloomberg-style single number card:

    +---------------------+
    | Sharpe              |
    |    1.28             |
    |    +0.06 vs. last   |
    +---------------------+

Variants are available through ``tone``: ``"neutral"`` / ``"success"`` /
``"warning"`` / ``"error"``. The tile is pure-Solara so it works everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import solara

from aqp.ui.theme import PALETTE

# Foreground must hit WCAG AA (>= 4.5) against the tile background.
# The previous values (e.g. warning ``#78350f`` on ``#fed7aa``) were
# legal but borderline.  The pairs below exceed AA by a comfortable
# margin while still looking soft.
_TONE_COLORS: dict[str, tuple[str, str]] = {
    "neutral": (PALETTE.bg_panel, PALETTE.text_inverse),
    "success": (PALETTE.success, PALETTE.success_fg),
    "warning": (PALETTE.warning, PALETTE.warning_fg),
    "error": (PALETTE.error, PALETTE.error_fg),
    "info": (PALETTE.info, PALETTE.info_fg),
}


@dataclass
class TileTrend:
    """Delta display on a tile — small number + arrow direction."""

    delta: float
    label: str = "Δ"
    better: Literal["up", "down"] = "up"

    def tone(self) -> str:
        if self.delta == 0:
            return "neutral"
        is_up = self.delta > 0
        if (is_up and self.better == "up") or (not is_up and self.better == "down"):
            return "success"
        return "error"

    def render(self) -> str:
        arrow = "▲" if self.delta > 0 else "▼" if self.delta < 0 else "•"
        return f"{arrow} {self.delta:+.2f} {self.label}"


@solara.component
def MetricTile(
    label: str,
    value: str | float | int | None,
    *,
    unit: str = "",
    hint: str | None = None,
    trend: TileTrend | None = None,
    tone: str = "neutral",
    min_width: str = "160px",
) -> None:
    bg, fg = _TONE_COLORS.get(tone, _TONE_COLORS["neutral"])
    value_str = _format_value(value, unit=unit)
    with solara.Column(
        gap="2px",
        style={
            "background": bg,
            "color": fg,
            "padding": "14px 16px",
            "border-radius": "12px",
            "box-shadow": "0 1px 2px rgba(0,0,0,0.18)",
            "min-width": min_width,
        },
    ):
        solara.Markdown(
            f"<div style='font-size:11px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.92'>{label}</div>"
        )
        solara.Markdown(
            f"<div style='font-size:26px;font-weight:700;line-height:1.1'>{value_str}</div>"
        )
        if trend is not None:
            trend_bg, trend_fg = _TONE_COLORS.get(trend.tone(), _TONE_COLORS["neutral"])
            solara.Markdown(
                f"<div style='font-size:12px;padding:2px 6px;border-radius:999px;"
                f"background:{trend_bg};color:{trend_fg};display:inline-block'>{trend.render()}</div>"
            )
        elif hint:
            solara.Markdown(
                f"<div style='font-size:12px;opacity:0.92'>{hint}</div>"
            )


def _format_value(value: str | float | int | None, *, unit: str) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if unit == "%":
            return f"{value * 100:.2f}%"
        if unit == "$":
            return f"${value:,.2f}"
        return f"{value:.4g}"
    return f"{value}{unit}"
