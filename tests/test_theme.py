"""Contrast + template tests for ``aqp.ui.theme``."""
from __future__ import annotations

import plotly.graph_objects as go
import pytest

from aqp.ui.theme import (
    CANDLE_COLORS,
    PALETTE,
    apply_theme,
    chip_style,
    contrast_ratio,
    plotly_template,
)


_AA_NORMAL = 4.5  # WCAG 2.1 AA for normal text
_AA_LARGE = 3.0   # WCAG 2.1 AA for large / bold text


# ---------------------------------------------------------------------------
# Contrast ratios
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fg,bg,minimum",
    [
        (PALETTE.text_primary, PALETTE.bg_page, _AA_NORMAL),
        (PALETTE.text_primary, PALETTE.bg_card, _AA_NORMAL),
        (PALETTE.text_secondary, PALETTE.bg_page, _AA_NORMAL),
        (PALETTE.text_muted, PALETTE.bg_page, _AA_NORMAL),
        (PALETTE.text_inverse, PALETTE.bg_panel, _AA_NORMAL),
        (PALETTE.success_fg, PALETTE.success, _AA_NORMAL),
        (PALETTE.error_fg, PALETTE.error, _AA_NORMAL),
        (PALETTE.warning_fg, PALETTE.warning, _AA_NORMAL),
        (PALETTE.info_fg, PALETTE.info, _AA_NORMAL),
        (PALETTE.accent_fg, PALETTE.accent, _AA_NORMAL),
        (PALETTE.candle_up_line, PALETTE.bg_card, _AA_LARGE),
        (PALETTE.candle_down_line, PALETTE.bg_card, _AA_LARGE),
    ],
)
def test_contrast_pairs_meet_wcag(fg: str, bg: str, minimum: float) -> None:
    ratio = contrast_ratio(fg, bg)
    assert ratio >= minimum, f"{fg} on {bg} is {ratio:.2f}; need >= {minimum}"


def test_contrast_ratio_is_symmetric() -> None:
    assert (
        contrast_ratio(PALETTE.text_primary, PALETTE.bg_page)
        == contrast_ratio(PALETTE.bg_page, PALETTE.text_primary)
    )


def test_contrast_ratio_white_vs_black_is_21() -> None:
    assert round(contrast_ratio("#ffffff", "#000000"), 1) == 21.0


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------


def test_plotly_template_light_sets_backgrounds() -> None:
    tpl = plotly_template(dark=False)
    assert tpl.layout.paper_bgcolor == PALETTE.bg_card
    assert tpl.layout.plot_bgcolor == PALETTE.bg_card
    assert tpl.layout.font.color == PALETTE.text_primary


def test_plotly_template_dark_flips_contrast() -> None:
    tpl = plotly_template(dark=True)
    assert tpl.layout.paper_bgcolor == PALETTE.bg_panel
    assert tpl.layout.font.color == PALETTE.text_inverse


def test_apply_theme_sets_candle_colors() -> None:
    fig = go.Figure(
        go.Candlestick(
            x=[1, 2], open=[1, 2], high=[2, 3], low=[0, 1], close=[1.5, 2.5]
        )
    )
    apply_theme(fig)
    trace = fig.data[0]
    assert trace.increasing.fillcolor == CANDLE_COLORS["up"]
    assert trace.decreasing.fillcolor == CANDLE_COLORS["down"]


def test_apply_theme_preserves_existing_candle_colors() -> None:
    fig = go.Figure(
        go.Candlestick(
            x=[1],
            open=[1],
            high=[2],
            low=[0],
            close=[1.5],
            increasing={"fillcolor": "#123456", "line": {"color": "#000000"}},
        )
    )
    apply_theme(fig)
    assert fig.data[0].increasing.fillcolor == "#123456"


# ---------------------------------------------------------------------------
# Chip helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tone",
    ["neutral", "success", "warning", "error", "info", "unknown"],
)
def test_chip_style_returns_css_dict(tone: str) -> None:
    style = chip_style(tone)
    assert "background-color" in style
    assert "color" in style
    # Unknown tone falls back to neutral colour pair.
    if tone == "unknown":
        assert style["background-color"] == PALETTE.bg_card_alt
