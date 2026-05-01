from __future__ import annotations

from datetime import datetime

import pyarrow as pa

from aqp.data import iceberg_catalog


def test_read_polars_wraps_read_arrow(monkeypatch) -> None:
    table = pa.table(
        {
            "timestamp": [
                datetime(2025, 1, 1),
                datetime(2025, 1, 2),
            ],
            "vt_symbol": ["SPY.NASDAQ", "QQQ.NASDAQ"],
            "close": [100.0, 200.0],
        }
    )

    monkeypatch.setattr(iceberg_catalog, "read_arrow", lambda *a, **k: table)

    df = iceberg_catalog.read_polars("aqp.prices")

    assert df is not None
    assert df.shape == (2, 3)
    assert df["vt_symbol"].to_list() == ["SPY.NASDAQ", "QQQ.NASDAQ"]
    assert df["close"].to_list() == [100.0, 200.0]
