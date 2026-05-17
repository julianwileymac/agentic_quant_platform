from __future__ import annotations

import types
import sys
from datetime import datetime, timezone

import pandas as pd
import pyarrow as pa

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.api.yfinance import YFinanceFetcher


def test_yfinance_class_attrs_set() -> None:
    assert YFinanceFetcher.PROVIDER_NAME == "yFinance"
    assert YFinanceFetcher.MEDALLION_LAYER == "bronze"
    assert YFinanceFetcher.REQUIRES_AUTH is False


def test_yfinance_normalize_schema_renames_columns() -> None:
    fetcher = YFinanceFetcher(symbols=["AAPL"])
    frame = pd.DataFrame(
        {
            "Date": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1000.0],
            "symbol": ["AAPL"],
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
    assert table.schema.field("timestamp").type == pa.timestamp("us", tz="UTC")


def test_yfinance_fetch_uses_batch_tickers(monkeypatch) -> None:
    called_with: list[str] = []

    class _FakeTicker:
        def __init__(self, symbol: str) -> None:
            self._symbol = symbol

        def history(self, **_: object) -> pd.DataFrame:
            index = pd.DatetimeIndex([datetime(2026, 1, 1, tzinfo=timezone.utc)])
            return pd.DataFrame(
                {
                    "Open": [100.0],
                    "High": [101.0],
                    "Low": [99.0],
                    "Close": [100.5],
                    "Volume": [1234.0],
                },
                index=index,
            )

    class _FakeTickers:
        def __init__(self, symbols_text: str) -> None:
            called_with.append(symbols_text)
            self.tickers = {
                symbol: _FakeTicker(symbol)
                for symbol in symbols_text.split()
            }

    fake_module = types.SimpleNamespace(Tickers=_FakeTickers)
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    fetcher = YFinanceFetcher(symbols=["AAPL", "MSFT"])
    ctx = NodeContext(
        pipeline_id="test",
        run_id="run-1",
        node_name="source.yfinance",
        node_index=0,
    )
    batches = list(fetcher.fetch(ctx))

    assert called_with == ["AAPL MSFT"]
    assert len(batches) == 2
