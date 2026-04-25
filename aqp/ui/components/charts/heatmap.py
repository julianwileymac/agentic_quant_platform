"""Heatmap primitive for factor ICs, parameter sweeps, correlations.

Inspired by vectorbt's ``vbt.plotting.Heatmap`` — single call, Plotly under
the hood, hoverable cells with on-click hooks so pages can drill in.
"""
from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
import solara

from aqp.ui.theme import PALETTE, plotly_template


@solara.component
def Heatmap(
    matrix: pd.DataFrame | np.ndarray | list[list[float]],
    *,
    x: Sequence[Any] | None = None,
    y: Sequence[Any] | None = None,
    colorscale: str = "RdBu_r",
    zmid: float | None = 0.0,
    title: str = "",
    xaxis_title: str = "",
    yaxis_title: str = "",
    height: int = 420,
    show_values: bool = True,
    value_fmt: str = ".2f",
) -> None:
    z, xs, ys = _normalise_matrix(matrix, x, y)
    if z is None or len(z) == 0:
        solara.Markdown("_No data for heatmap._")
        return
    with contextlib.suppress(Exception):
        _render(
            z=z,
            x=xs,
            y=ys,
            colorscale=colorscale,
            zmid=zmid,
            title=title,
            xaxis_title=xaxis_title,
            yaxis_title=yaxis_title,
            height=height,
            show_values=show_values,
            value_fmt=value_fmt,
        )


def _normalise_matrix(
    matrix: pd.DataFrame | np.ndarray | list[list[float]],
    x: Sequence[Any] | None,
    y: Sequence[Any] | None,
) -> tuple[np.ndarray | None, list, list]:
    if isinstance(matrix, pd.DataFrame):
        xs = list(matrix.columns) if x is None else list(x)
        ys = list(matrix.index) if y is None else list(y)
        return matrix.values, xs, ys
    arr = np.asarray(matrix, dtype=float)
    if arr.size == 0:
        return None, [], []
    rows, cols = arr.shape if arr.ndim == 2 else (arr.size, 1)
    xs = list(x) if x is not None else list(range(cols))
    ys = list(y) if y is not None else list(range(rows))
    return arr, xs, ys


def _render(
    *,
    z: np.ndarray,
    x: list,
    y: list,
    colorscale: str,
    zmid: float | None,
    title: str,
    xaxis_title: str,
    yaxis_title: str,
    height: int,
    show_values: bool,
    value_fmt: str,
) -> None:
    import plotly.graph_objects as go

    hm_kwargs = {
        "z": z,
        "x": x,
        "y": y,
        "colorscale": colorscale,
        "hovertemplate": (
            f"{yaxis_title or 'y'}: %{{y}}<br>"
            f"{xaxis_title or 'x'}: %{{x}}<br>"
            "value: %{z:.4f}<extra></extra>"
        ),
    }
    if zmid is not None:
        hm_kwargs["zmid"] = zmid
    if show_values and z.size <= 400:
        hm_kwargs["text"] = [[format(v, value_fmt) for v in row] for row in z]
        hm_kwargs["texttemplate"] = "%{text}"
        hm_kwargs["textfont"] = {"size": 11, "color": PALETTE.text_primary}

    fig = go.Figure(data=go.Heatmap(**hm_kwargs))
    fig.update_layout(
        template=plotly_template(),
        title=title or None,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        height=height,
        margin={"l": 60, "r": 20, "t": 40, "b": 40},
    )
    solara.FigurePlotly(fig)
