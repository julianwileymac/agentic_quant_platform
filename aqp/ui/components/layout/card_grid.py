"""Bento-style card grid.

Used by the Dashboard Home to lay out a dense, asymmetric grid of KPIs,
tables, and panels. Cards can span multiple columns via the ``span``
parameter, mirroring CSS grid's ``grid-column`` syntax.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import solara


@dataclass
class CardSpec:
    key: str
    render: Callable[[], None]
    title: str | None = None
    span: int = 1   # number of columns this card spans
    min_height: str = "0"


@solara.component
def CardGrid(
    cards: Iterable[CardSpec],
    *,
    columns: int = 4,
    gap: str = "14px",
    padding: str = "0",
) -> None:
    card_list = list(cards)
    if not card_list:
        return
    cols = max(1, min(int(columns), 12))
    grid_template = f"repeat({cols}, minmax(0, 1fr))"

    with solara.Div(
        style={
            "display": "grid",
            "grid-template-columns": grid_template,
            "grid-auto-rows": "minmax(120px, auto)",
            "gap": gap,
            "padding": padding,
        }
    ):
        for card in card_list:
            span = max(1, min(int(card.span), cols))
            with solara.Div(
                style={
                    "grid-column": f"span {span}",
                    "background": "#0f172a",
                    "color": "#e2e8f0",
                    "border-radius": "12px",
                    "padding": "16px",
                    "box-shadow": "0 1px 2px rgba(0,0,0,0.18)",
                    "min-height": card.min_height,
                    "display": "flex",
                    "flex-direction": "column",
                    "gap": "8px",
                    "overflow": "hidden",
                }
            ):
                if card.title:
                    solara.Markdown(
                        f"<div style='font-size:12px;text-transform:uppercase;"
                        f"letter-spacing:0.08em;opacity:0.7'>{card.title}</div>"
                    )
                card.render()
