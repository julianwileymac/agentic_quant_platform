from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyarrow as pa
import pytest

from aqp.data.fabric.schema_registry import FeatureSchema, OHLCVSchema
from aqp.dagster.ops.ta_ops import (
    _bollinger_bands,
    _macd,
    _moving_averages,
    _rsi,
)

dg = pytest.importorskip("dagster")


def _require_ta_backend() -> None:
    try:
        import vectorbtpro  # noqa: F401
    except ImportError:
        try:
            import pandas_ta  # noqa: F401
        except ImportError:
            pytest.importorskip("pandas_ta_classic")


def _sample_ohlcv_table() -> pa.Table:
    rows: list[dict[str, object]] = []
    symbols = ("AAPL", "MSFT", "NVDA")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 80 days covers MACD's slow_window (26) + signal_window (9) plus headroom.
    for day in range(80):
        ts = start + timedelta(days=day)
        for idx, symbol in enumerate(symbols):
            base = 100.0 + (idx * 10.0) + float(day)
            rows.append(
                {
                    "symbol": symbol,
                    "source_feed_id": "source.yfinance",
                    "timestamp": ts,
                    "open": base,
                    "high": base + 1.5,
                    "low": base - 1.0,
                    "close": base + 0.75,
                    "volume": 1_000.0 + (float(day) * 10.0) + idx,
                }
            )
    return OHLCVSchema.validate_table(pa.Table.from_pylist(rows))


def test_moving_averages_smoke() -> None:
    _require_ta_backend()
    table = _sample_ohlcv_table()
    out = _moving_averages(table, {"windows": [5], "pipeline_version": "test"})
    FeatureSchema.validate_table(out)
    assert int(out.num_rows) > 0
    assert set(out.column("feature_name").to_pylist()) == {"sma_5"}


def test_rsi_emits_feature_schema() -> None:
    _require_ta_backend()
    table = _sample_ohlcv_table()
    out = _rsi(table, {"window": 14, "pipeline_version": "test"})
    FeatureSchema.validate_table(out)
    assert int(out.num_rows) > 0
    assert set(out.column("feature_name").to_pylist()) == {"rsi_14"}


def test_bollinger_bands_emits_three_features() -> None:
    _require_ta_backend()
    table = _sample_ohlcv_table()
    out = _bollinger_bands(table, {"window": 20, "std": 2.0, "pipeline_version": "test"})
    FeatureSchema.validate_table(out)
    names = set(out.column("feature_name").to_pylist())
    assert {
        "bb_upper_20_2.0",
        "bb_middle_20_2.0",
        "bb_lower_20_2.0",
    }.issubset(names)


def test_macd_emits_three_features() -> None:
    _require_ta_backend()
    table = _sample_ohlcv_table()
    out = _macd(
        table,
        {
            "fast_window": 12,
            "slow_window": 26,
            "signal_window": 9,
            "pipeline_version": "test",
        },
    )
    FeatureSchema.validate_table(out)
    names = set(out.column("feature_name").to_pylist())
    assert {"macd_12_26", "macd_signal_9", "macd_hist"}.issubset(names)


def test_materialize_features_job_definition_exists() -> None:
    from aqp.dagster.assets.feature_materializer import materialize_features

    assert isinstance(materialize_features, dg.JobDefinition)
