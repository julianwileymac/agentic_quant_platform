"""Smoke tests for the FinRL ``DataProcessor`` parity layer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp_rl.core.data import BaseDataPipeline, DataPipelineResult


class _StubPipeline(BaseDataPipeline):
    def __init__(self) -> None:
        super().__init__()

    def download_data(self, ticker_list, start, end, time_interval="1D"):
        rows = []
        for tic in ticker_list:
            for i in range(5):
                rows.append(
                    {
                        "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                        "tic": tic,
                        "open": 100 + i,
                        "high": 101 + i,
                        "low": 99 + i,
                        "close": 100 + i,
                        "volume": 1000 + i * 10,
                    }
                )
        return pd.DataFrame(rows)


def test_run_full_returns_bundle_shapes():
    pipeline = _StubPipeline()
    result = pipeline.run_full(
        ticker_list=["AAA", "BBB"],
        start="2024-01-01",
        end="2024-01-10",
        tech_indicator_list=[],
        use_vix=False,
        use_turbulence=False,
    )
    assert isinstance(result, DataPipelineResult)
    assert result.df is not None
    assert result.price_array.shape[0] > 0
    assert result.tech_array.shape[0] == result.price_array.shape[0]


def test_time_split_filters_inclusively_lower_bound():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-05", "2024-01-10"]),
            "tic": ["AAA"] * 3,
            "close": [100, 105, 110],
        }
    )
    out = BaseDataPipeline.time_split(df, "2024-01-02", "2024-01-09")
    assert list(out["close"]) == [105]


def test_clean_data_drops_nan():
    pipeline = _StubPipeline()
    df = pipeline.download_data(["XYZ"], "2024-01-01", "2024-01-05")
    df.loc[0, "close"] = float("nan")
    cleaned = pipeline.clean_data(df)
    assert not cleaned.isna().any().any()
