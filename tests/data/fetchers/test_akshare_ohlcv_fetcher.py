from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from aqp.data.fabric.schema_registry import OHLCVSchema
from aqp.data.fetchers.api.akshare_ohlcv import AkshareOHLCVFetcher


def test_chinese_column_rename() -> None:
    fetcher = AkshareOHLCVFetcher(symbols=["600000"])
    frame = pd.DataFrame(
        {
            "日期": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
            "开盘": [10.0],
            "收盘": [11.0],
            "最高": [12.0],
            "最低": [9.0],
            "成交量": [1000.0],
            "成交额": [100000.0],
        }
    )

    table = fetcher.normalize_schema(frame)

    assert table.column_names == [
        "symbol",
        "source_feed_id",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_normalize_schema_emits_ohlcv_schema() -> None:
    fetcher = AkshareOHLCVFetcher(symbols=["600000"])
    frame = pd.DataFrame(
        {
            "timestamp": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [1000.0],
            "symbol": ["600000"],
            "source_feed_id": ["akshare"],
        }
    )

    table = fetcher.normalize_schema(frame)

    assert table.schema == OHLCVSchema.CANONICAL_SCHEMA
