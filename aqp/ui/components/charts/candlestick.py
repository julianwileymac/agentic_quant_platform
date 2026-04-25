"""Candlestick + volume + overlay widget.

Used by the Data Browser, the unified Live Market security view, and the
Indicator Builder.  The overlay API is intentionally tiny: a list of
:class:`IndicatorOverlay` objects, each with a column name and an
optional panel hint so multi-pane charts (price + RSI + MACD) work out
of the box.

The module also exports :func:`build_security_figure`, a batteries-included
helper that takes raw OHLCV bars + a flat list of toggle flags (``sma_20``,
``ema_20``, ``vwap``, ``bbands``, ``rsi``, ``macd``, ``volume``,
``drawdown``) and returns a styled ``plotly.graph_objects.Figure``.  The
Live Market page uses it directly; callers who want finer control can
still build their own ``overlays`` list and hand them to
:class:`Candlestick`.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
import solara

from aqp.ui.theme import CANDLE_COLORS, PALETTE, apply_theme, plotly_template


@dataclass
class IndicatorOverlay:
    """Pairs a DataFrame column name with its preferred visual treatment."""

    column: str
    label: str | None = None
    panel: str = "price"  # "price" | "oscillator" | "volume" | custom name
    dash: str = "solid"   # plotly line.dash
    width: float = 1.5
    color: str | None = None  # None = let Plotly pick
    secondary_y: bool = False
    fill_between: tuple[str, str] | None = None  # (other_column, ...) for bands

    def render_label(self) -> str:
        return self.label or self.column

    def tags(self) -> list[str]:
        return [self.panel] if self.panel else []


@solara.component
def Candlestick(
    bars: pd.DataFrame,
    *,
    title: str = "",
    overlays: list[IndicatorOverlay] | None = None,
    show_volume: bool = True,
    show_range_slider: bool = True,
    height: int = 480,
    dark: bool = False,
) -> None:
    if bars is None or bars.empty:
        solara.Markdown("_No bars to plot._")
        return
    with contextlib.suppress(Exception):
        _render(
            bars=bars,
            title=title,
            overlays=overlays or [],
            show_volume=show_volume,
            show_range_slider=show_range_slider,
            height=height,
            dark=dark,
        )


def _render(
    *,
    bars: pd.DataFrame,
    title: str,
    overlays: list[IndicatorOverlay],
    show_volume: bool,
    show_range_slider: bool,
    height: int,
    dark: bool = False,
) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # Partition overlays into panels (price / volume / oscillator / custom).
    panels = _organise_panels(overlays, show_volume=show_volume, has_volume="volume" in bars.columns)
    if not panels:
        panels = ["price"]
    n = len(panels)
    heights = _panel_heights(panels)

    fig = make_subplots(
        rows=n,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=heights,
    )

    fig.add_trace(
        go.Candlestick(
            x=bars["timestamp"],
            open=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            name="OHLC",
            showlegend=False,
            increasing={
                "fillcolor": CANDLE_COLORS["up"],
                "line": {"color": CANDLE_COLORS["up_line"]},
            },
            decreasing={
                "fillcolor": CANDLE_COLORS["down"],
                "line": {"color": CANDLE_COLORS["down_line"]},
            },
        ),
        row=panels.index("price") + 1,
        col=1,
    )

    for ov in overlays:
        if ov.column not in bars.columns:
            continue
        panel = ov.panel if ov.panel in panels else "price"
        row = panels.index(panel) + 1
        fig.add_trace(
            go.Scatter(
                x=bars["timestamp"],
                y=bars[ov.column],
                mode="lines",
                name=ov.render_label(),
                line={"dash": ov.dash, "width": ov.width, **({"color": ov.color} if ov.color else {})},
            ),
            row=row,
            col=1,
        )

    if show_volume and "volume" in panels:
        fig.add_trace(
            go.Bar(
                x=bars["timestamp"],
                y=bars["volume"],
                name="Volume",
                marker={"color": PALETTE.volume},
                showlegend=False,
            ),
            row=panels.index("volume") + 1,
            col=1,
        )

    fig.update_layout(
        template=plotly_template(dark=dark),
        title=title or None,
        height=height,
        margin={"l": 52, "r": 20, "t": 40, "b": 30},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        xaxis_rangeslider_visible=show_range_slider and n == 1,
    )
    if n > 1:
        # Range slider duplication across panels is ugly — hide on subpanels.
        fig.update_xaxes(rangeslider_visible=False)
    solara.FigurePlotly(fig)


def _organise_panels(
    overlays: list[IndicatorOverlay],
    *,
    show_volume: bool,
    has_volume: bool,
) -> list[str]:
    panels: list[str] = ["price"]
    for ov in overlays:
        if ov.panel not in panels and ov.panel != "price":
            if ov.panel == "volume" and (not show_volume or not has_volume):
                continue
            panels.append(ov.panel)
    if show_volume and has_volume and "volume" not in panels:
        panels.append("volume")
    return panels


def _panel_heights(panels: list[str]) -> list[float]:
    weights = []
    for p in panels:
        if p == "price":
            weights.append(0.6)
        elif p == "volume":
            weights.append(0.12)
        else:
            weights.append(0.18)
    total = sum(weights) or 1.0
    return [w / total for w in weights]


# ---------------------------------------------------------------------------
# Builder helper — Live Market security view
# ---------------------------------------------------------------------------


_SUPPORTED_FEATURES = {
    "sma_20",
    "sma_50",
    "ema_20",
    "ema_50",
    "bbands",
    "vwap",
    "volume",
    "rsi",
    "macd",
    "drawdown",
}


def build_security_figure(
    bars: pd.DataFrame,
    *,
    features: Iterable[str] = (),
    title: str | None = None,
    height: int = 560,
    dark: bool = False,
    show_range_slider: bool = False,
):
    """Return a themed ``plotly.graph_objects.Figure`` for a security view.

    Parameters
    ----------
    bars
        Tidy OHLCV frame with columns ``timestamp, open, high, low, close,
        volume`` (``volume`` optional).
    features
        Set of feature toggles.  Unknown names are silently ignored so the
        caller can pass UI state without sanitising first.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if bars is None or bars.empty:
        fig = go.Figure()
        fig.update_layout(template=plotly_template(dark=dark), height=height, title=title or "")
        fig.add_annotation(
            text="No data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"color": PALETTE.text_muted, "size": 14},
        )
        return fig

    wanted = {f.lower() for f in features} & _SUPPORTED_FEATURES
    df = bars.copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Compute derived columns up-front.
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float) if "volume" in df.columns else None

    if "sma_20" in wanted:
        df["sma_20"] = close.rolling(20, min_periods=1).mean()
    if "sma_50" in wanted:
        df["sma_50"] = close.rolling(50, min_periods=1).mean()
    if "ema_20" in wanted:
        df["ema_20"] = close.ewm(span=20, adjust=False).mean()
    if "ema_50" in wanted:
        df["ema_50"] = close.ewm(span=50, adjust=False).mean()
    if "bbands" in wanted:
        m = close.rolling(20, min_periods=1).mean()
        s = close.rolling(20, min_periods=1).std(ddof=0).fillna(0.0)
        df["bb_mid"] = m
        df["bb_up"] = m + 2.0 * s
        df["bb_down"] = m - 2.0 * s
    if "vwap" in wanted and volume is not None:
        typical = (high + low + close) / 3.0
        cum_vol = volume.cumsum().replace(0, np.nan)
        df["vwap"] = (typical * volume).cumsum() / cum_vol

    if "rsi" in wanted:
        delta = close.diff()
        up = delta.clip(lower=0.0)
        down = -delta.clip(upper=0.0)
        avg_up = up.ewm(alpha=1 / 14, adjust=False).mean()
        avg_down = down.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan)
        rs = avg_up / avg_down
        df["rsi_14"] = (100 - (100 / (1 + rs))).fillna(50.0)
    if "macd" in wanted:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df["macd"] = macd
        df["macd_signal"] = signal
        df["macd_hist"] = macd - signal
    if "drawdown" in wanted:
        running_max = close.cummax().replace(0, np.nan)
        df["drawdown"] = (close / running_max - 1.0) * 100.0

    show_volume = "volume" in wanted and volume is not None
    include_rsi = "rsi" in wanted
    include_macd = "macd" in wanted
    include_dd = "drawdown" in wanted

    panels: list[tuple[str, float]] = [("price", 0.55)]
    if show_volume:
        panels.append(("volume", 0.12))
    if include_rsi:
        panels.append(("rsi", 0.14))
    if include_macd:
        panels.append(("macd", 0.14))
    if include_dd:
        panels.append(("drawdown", 0.12))

    total_weight = sum(w for _, w in panels)
    row_heights = [w / total_weight for _, w in panels]

    fig = make_subplots(
        rows=len(panels),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=row_heights,
        subplot_titles=[label.upper() for label, _ in panels],
    )

    row_for_name = {name: idx + 1 for idx, (name, _) in enumerate(panels)}

    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="OHLC",
            showlegend=False,
            increasing={
                "fillcolor": CANDLE_COLORS["up"],
                "line": {"color": CANDLE_COLORS["up_line"]},
            },
            decreasing={
                "fillcolor": CANDLE_COLORS["down"],
                "line": {"color": CANDLE_COLORS["down_line"]},
            },
        ),
        row=1,
        col=1,
    )

    # Price-pane overlays
    _add_price_overlay(fig, df, "sma_20", PALETTE.sma, "SMA(20)", dash="solid")
    _add_price_overlay(fig, df, "sma_50", PALETTE.info, "SMA(50)", dash="dot")
    _add_price_overlay(fig, df, "ema_20", PALETTE.ema, "EMA(20)", dash="dashdot")
    _add_price_overlay(fig, df, "ema_50", PALETTE.warning, "EMA(50)", dash="dashdot")
    if "bb_up" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["bb_up"],
                name="BB Upper",
                line={"color": PALETTE.bb_band, "width": 1.0, "dash": "dot"},
                mode="lines",
                showlegend=True,
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["bb_down"],
                name="BB Lower",
                line={"color": PALETTE.bb_band, "width": 1.0, "dash": "dot"},
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(148, 163, 184, 0.12)",
                showlegend=True,
            ),
            row=1,
            col=1,
        )
    _add_price_overlay(fig, df, "vwap", PALETTE.vwap, "VWAP", dash="solid", width=1.2)

    # Volume panel
    if show_volume and "volume" in row_for_name:
        # Color volume bars by up/down close for quick read.
        up_mask = df["close"] >= df["open"]
        colors = [PALETTE.candle_up if u else PALETTE.candle_down for u in up_mask]
        fig.add_trace(
            go.Bar(
                x=df["timestamp"],
                y=df["volume"],
                name="Volume",
                marker={"color": colors, "line": {"width": 0}},
                opacity=0.55,
                showlegend=False,
            ),
            row=row_for_name["volume"],
            col=1,
        )

    # RSI panel
    if include_rsi and "rsi" in row_for_name:
        row = row_for_name["rsi"]
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["rsi_14"],
                name="RSI(14)",
                line={"color": PALETTE.rsi, "width": 1.4},
                showlegend=False,
            ),
            row=row,
            col=1,
        )
        for level, color in ((30, PALETTE.success), (70, PALETTE.error)):
            fig.add_shape(
                type="line",
                x0=df["timestamp"].iloc[0],
                x1=df["timestamp"].iloc[-1],
                y0=level,
                y1=level,
                xref=f"x{row}",
                yref=f"y{row}",
                line={"dash": "dot", "width": 1, "color": color},
            )
        fig.update_yaxes(range=[0, 100], row=row, col=1)

    # MACD panel
    if include_macd and "macd" in row_for_name:
        row = row_for_name["macd"]
        fig.add_trace(
            go.Bar(
                x=df["timestamp"],
                y=df["macd_hist"],
                name="Hist",
                marker={
                    "color": [
                        PALETTE.candle_up if h >= 0 else PALETTE.candle_down
                        for h in df["macd_hist"].fillna(0)
                    ]
                },
                opacity=0.5,
                showlegend=False,
            ),
            row=row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["macd"],
                name="MACD",
                line={"color": PALETTE.macd, "width": 1.3},
                showlegend=False,
            ),
            row=row,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["macd_signal"],
                name="Signal",
                line={"color": PALETTE.macd_signal, "width": 1.3, "dash": "dot"},
                showlegend=False,
            ),
            row=row,
            col=1,
        )

    # Drawdown panel
    if include_dd and "drawdown" in row_for_name:
        row = row_for_name["drawdown"]
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["drawdown"],
                name="Drawdown (%)",
                fill="tozeroy",
                line={"color": PALETTE.drawdown, "width": 1.2},
                fillcolor="rgba(185, 28, 28, 0.22)",
                showlegend=False,
            ),
            row=row,
            col=1,
        )

    fig.update_layout(
        template=plotly_template(dark=dark),
        title=title or None,
        height=height,
        margin={"l": 52, "r": 20, "t": 50, "b": 30},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        xaxis_rangeslider_visible=show_range_slider and len(panels) == 1,
    )
    if len(panels) > 1:
        fig.update_xaxes(rangeslider_visible=False)

    # Tone the subplot titles to match the theme (they default to black/white).
    annotations = list(fig.layout.annotations or [])
    color = PALETTE.text_inverse if dark else PALETTE.text_secondary
    for ann in annotations:
        ann.update(font={"color": color, "size": 11})
    fig.update_layout(annotations=annotations)

    return fig


def _add_price_overlay(
    fig,
    df: pd.DataFrame,
    column: str,
    color: str,
    label: str,
    *,
    dash: str = "solid",
    width: float = 1.4,
) -> None:
    import plotly.graph_objects as go

    if column not in df.columns:
        return
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df[column],
            name=label,
            line={"color": color, "width": width, "dash": dash},
            mode="lines",
            showlegend=True,
        ),
        row=1,
        col=1,
    )


SUPPORTED_CHART_FEATURES = tuple(sorted(_SUPPORTED_FEATURES))


__all__ = [
    "Candlestick",
    "IndicatorOverlay",
    "build_security_figure",
    "SUPPORTED_CHART_FEATURES",
]
