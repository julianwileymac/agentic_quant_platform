"""Tests for :mod:`aqp.data.parquet_inspector`."""
from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from aqp.data.parquet_inspector import inspect_root


def _write_parquet(path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df), str(path))


def test_inspect_missing_root(tmp_path):
    report = inspect_root(tmp_path / "does-not-exist")
    assert report.exists is False
    assert report.error == "path does not exist"


def test_inspect_flat_layout(tmp_path):
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=3),
            "vt_symbol": ["AAPL.NASDAQ"] * 3,
            "open": [1.0, 2.0, 3.0],
            "high": [1.0, 2.0, 3.0],
            "low": [1.0, 2.0, 3.0],
            "close": [1.0, 2.0, 3.0],
            "volume": [10.0, 20.0, 30.0],
        }
    )
    _write_parquet(tmp_path / "AAPL.parquet", df)

    report = inspect_root(tmp_path)
    assert report.exists
    assert report.file_count == 1
    assert report.hive_partitioning is False
    assert "open" in report.columns
    assert report.suggested_column_map.get("close") == "close"
    assert report.suggested_column_map.get("vt_symbol") == "vt_symbol"


def test_inspect_hive_layout(tmp_path):
    df = pd.DataFrame({"px": [1.0, 2.0], "ticker": ["AAA", "BBB"]})
    _write_parquet(tmp_path / "year=2024" / "month=01" / "part-0.parquet", df)
    _write_parquet(tmp_path / "year=2024" / "month=02" / "part-0.parquet", df)
    _write_parquet(tmp_path / "year=2025" / "month=01" / "part-0.parquet", df)

    report = inspect_root(tmp_path)
    assert report.exists
    assert report.hive_partitioning is True
    keys = {p.key for p in report.partition_keys}
    assert keys == {"year", "month"}
    assert report.suggested_glob == "**/*.parquet"
    # The heuristic maps "ticker" -> vt_symbol
    assert report.suggested_column_map.get("vt_symbol") == "ticker"


def test_inspect_no_files(tmp_path):
    (tmp_path / "empty").mkdir()
    report = inspect_root(tmp_path / "empty")
    assert report.exists
    assert report.file_count == 0
    assert "no parquet files" in (report.error or "")
