"""Two-column / two-row split-pane layout primitive.

Used by Data Browser (symbol picker ← → candlestick), Crew Trace (run list
← → event stream), and ML Model Detail (model list ← → detail). Solara
does not ship a resizable splitter; this component renders a CSS flex pair
with a fixed ratio which is plenty for our dashboard use-cases.
"""
from __future__ import annotations

from collections.abc import Callable

import solara


@solara.component
def SplitPane(
    left: Callable[[], None],
    right: Callable[[], None],
    *,
    orientation: str = "horizontal",
    left_width: str = "320px",
    right_width: str = "auto",
    gap: str = "14px",
    sticky_left: bool = True,
) -> None:
    if orientation == "vertical":
        _vertical(top=left, bottom=right, gap=gap)
        return

    with solara.Row(
        gap=gap,
        style={"align-items": "stretch", "flex-wrap": "nowrap"},
    ):
        left_style = {
            "width": left_width,
            "flex": f"0 0 {left_width}",
            "min-width": "0",
        }
        if sticky_left:
            left_style.update({"position": "sticky", "top": "64px", "align-self": "flex-start"})
        with solara.Div(style=left_style):
            left()
        with solara.Div(
            style={
                "flex": "1",
                "min-width": "0",
                "max-width": right_width,
            }
        ):
            right()


def _vertical(
    top: Callable[[], None],
    bottom: Callable[[], None],
    gap: str,
) -> None:
    with solara.Column(gap=gap, style={"flex": "1"}):
        top()
        bottom()
