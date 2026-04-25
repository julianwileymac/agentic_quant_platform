"""Dense stats grid used by tear-sheet pages.

Turns a flat ``{"Sharpe": 1.28, "Sortino": 1.5, ...}`` into a row of
:class:`MetricTile` s. Built on top of MetricTile rather than inventing yet
another tile, so styling stays consistent across the platform.
"""
from __future__ import annotations

from typing import Any

import solara

from aqp.ui.components.data.metric_tile import MetricTile


@solara.component
def StatsGrid(
    stats: dict[str, Any],
    *,
    order: list[str] | None = None,
    columns: int = 4,
    units: dict[str, str] | None = None,
    tones: dict[str, str] | None = None,
) -> None:
    """Render a flex grid of metric tiles.

    Parameters
    ----------
    stats:
        ``{label: value}`` — a tile is produced per entry.
    order:
        Optional key ordering. Unlisted keys follow in insertion order.
    columns:
        Target number of tiles per row (controls min-width).
    units / tones:
        Per-key overrides forwarded to :class:`MetricTile`.
    """
    if not stats:
        solara.Markdown("_No stats to display._")
        return

    keys: list[str] = []
    if order:
        keys.extend(k for k in order if k in stats)
    keys.extend(k for k in stats if k not in keys)

    min_w = _min_width(columns)
    units = units or {}
    tones = tones or {}

    with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
        for key in keys:
            MetricTile(
                label=key,
                value=stats.get(key),
                unit=units.get(key, ""),
                tone=tones.get(key, "neutral"),
                min_width=min_w,
            )


def _min_width(columns: int) -> str:
    # Empirical: 180px per column is comfortable on a 1200px canvas.
    columns = max(1, min(int(columns), 8))
    return f"calc({100 / columns:.1f}% - 12px)"
