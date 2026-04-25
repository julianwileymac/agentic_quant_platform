"""Tests for ``build_security_figure`` (the unified OHLCV chart helper)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from aqp.ui.components import SUPPORTED_CHART_FEATURES, build_security_figure


@pytest.fixture
def synthetic_bars() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=120)
    returns = rng.normal(0.0005, 0.015, size=len(dates))
    close = 100 * (1 + pd.Series(returns)).cumprod().values
    high = close * (1 + rng.uniform(0, 0.01, len(dates)))
    low = close * (1 - rng.uniform(0, 0.01, len(dates)))
    open_ = low + rng.uniform(0, 1, len(dates)) * (high - low)
    volume = rng.integers(1_000_000, 10_000_000, len(dates)).astype(float)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def test_empty_bars_returns_figure_with_annotation() -> None:
    fig = build_security_figure(pd.DataFrame(), features=["sma_20"], title="x")
    assert isinstance(fig, go.Figure)
    # Empty figure still renders a "No data available" annotation
    assert any("No data" in (a.text or "") for a in fig.layout.annotations)


def test_builds_price_only_with_no_features(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features=[])
    # One trace: Candlestick
    assert len(fig.data) == 1
    assert fig.data[0].type == "candlestick"


def test_includes_sma_trace(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features={"sma_20", "sma_50"})
    names = [t.name for t in fig.data]
    assert "SMA(20)" in names
    assert "SMA(50)" in names


def test_volume_panel_adds_bar_trace(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features={"volume"})
    types = [t.type for t in fig.data]
    assert "bar" in types


def test_rsi_panel_adds_bounds(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features={"rsi"})
    names = [t.name for t in fig.data]
    assert "RSI(14)" in names
    # Two horizontal lines for 30/70 thresholds
    assert sum(1 for s in (fig.layout.shapes or []) if s.type == "line") >= 2


def test_macd_panel_has_three_traces(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features={"macd"})
    names = [t.name for t in fig.data]
    assert "MACD" in names
    assert "Signal" in names
    assert "Hist" in names


def test_drawdown_panel_renders_area(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features={"drawdown"})
    names = [t.name for t in fig.data]
    assert "Drawdown (%)" in names


def test_bbands_overlays_upper_and_lower(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features={"bbands"})
    names = [t.name for t in fig.data]
    assert "BB Upper" in names
    assert "BB Lower" in names


def test_vwap_overlay_requires_volume(synthetic_bars: pd.DataFrame) -> None:
    # Drop volume -> VWAP cannot be computed but should not raise.
    fig = build_security_figure(synthetic_bars.drop(columns=["volume"]), features={"vwap"})
    assert isinstance(fig, go.Figure)


def test_unknown_feature_is_silently_ignored(synthetic_bars: pd.DataFrame) -> None:
    fig = build_security_figure(synthetic_bars, features={"not_a_real_one", "sma_20"})
    names = [t.name for t in fig.data]
    assert "SMA(20)" in names


def test_supported_features_roster_is_exposed() -> None:
    expected = {
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
    assert set(SUPPORTED_CHART_FEATURES) == expected
