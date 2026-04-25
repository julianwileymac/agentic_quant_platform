"""Tests for MapFile + FactorFile."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from aqp.core.corporate_actions import (
    FactorFile,
    MapFile,
)


def test_map_file_ticker_at(tmp_path: Path):
    path = tmp_path / "FB.csv"
    path.write_text("2020-01-01,FB\n2021-10-28,META\n", encoding="utf-8")
    mf = MapFile.load(path)
    assert mf.ticker_at(date(2020, 6, 1)) == "FB"
    assert mf.ticker_at(date(2021, 12, 1)) == "META"


def test_factor_file_adjust_bars(tmp_path: Path):
    path = tmp_path / "AAPL.csv"
    # 2-for-1 split on 2020-06-15 (price_factor stays 1.0 unless dividends).
    path.write_text("2020-01-01,1.0,2.0\n", encoding="utf-8")
    ff = FactorFile.load(path)
    bars = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2020-03-01"), pd.Timestamp("2021-01-02")],
            "vt_symbol": ["AAPL.NASDAQ", "AAPL.NASDAQ"],
            "open": [100.0, 150.0],
            "high": [110.0, 160.0],
            "low": [90.0, 140.0],
            "close": [105.0, 155.0],
            "volume": [1000.0, 2000.0],
        }
    )
    adjusted = ff.adjust_bars(bars, mode="adjusted")
    # Both rows should have their close multiplied by 2.
    assert adjusted["close"].tolist() == [210.0, 310.0]
    assert adjusted["volume"].tolist() == [500.0, 1000.0]


def test_factor_file_raw_mode_noop(tmp_path: Path):
    path = tmp_path / "AAPL.csv"
    path.write_text("2020-01-01,1.0,2.0\n", encoding="utf-8")
    ff = FactorFile.load(path)
    bars = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2020-03-01")],
            "vt_symbol": ["AAPL.NASDAQ"],
            "open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0],
            "volume": [1000.0],
        }
    )
    adjusted = ff.adjust_bars(bars, mode="raw")
    pd.testing.assert_frame_equal(adjusted, bars)
