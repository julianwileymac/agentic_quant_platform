"""Local-drive data loading tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aqp.data.ingestion import (
    LocalCSVSource,
    LocalDirectoryLoader,
    LocalParquetSource,
)


def _make_csv(dir_: Path, name: str, dates: list[str]) -> Path:
    path = dir_ / f"{name}.csv"
    pd.DataFrame(
        {
            "Date": dates,
            "Open": [100 + i for i in range(len(dates))],
            "High": [101 + i for i in range(len(dates))],
            "Low": [99 + i for i in range(len(dates))],
            "Close": [100.5 + i for i in range(len(dates))],
            "Volume": [1000 + i * 10 for i in range(len(dates))],
        }
    ).to_csv(path, index=False)
    return path


def test_local_csv_source_basic(tmp_path: Path) -> None:
    _make_csv(tmp_path, "AAPL_NASDAQ", ["2024-01-02", "2024-01-03", "2024-01-04"])
    _make_csv(tmp_path, "MSFT_NASDAQ", ["2024-01-02", "2024-01-03", "2024-01-04"])
    source = LocalCSVSource(tmp_path)
    df = source.fetch()
    assert not df.empty
    assert set(df.columns) == {
        "timestamp",
        "vt_symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    assert set(df["vt_symbol"].unique()) == {"AAPL.NASDAQ", "MSFT.NASDAQ"}
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


def test_local_csv_source_symbol_filter_and_dates(tmp_path: Path) -> None:
    _make_csv(tmp_path, "AAPL_NASDAQ", ["2024-01-02", "2024-01-03", "2024-01-04"])
    _make_csv(tmp_path, "MSFT_NASDAQ", ["2024-01-02", "2024-01-03", "2024-01-04"])
    source = LocalCSVSource(tmp_path)
    df = source.fetch(
        symbols={"AAPL.NASDAQ"},
        start="2024-01-03",
        end="2024-01-03",
    )
    assert df["vt_symbol"].unique().tolist() == ["AAPL.NASDAQ"]
    assert len(df) == 1


def test_local_parquet_source(tmp_path: Path) -> None:
    pq_file = tmp_path / "SPY_NASDAQ.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [450.0, 451.0],
            "high": [451.0, 452.0],
            "low": [449.0, 450.0],
            "close": [450.5, 451.5],
            "volume": [1000000, 1100000],
        }
    ).to_parquet(pq_file)
    source = LocalParquetSource(tmp_path)
    df = source.fetch()
    assert len(df) == 2
    assert df["vt_symbol"].iloc[0] == "SPY.NASDAQ"


def test_local_directory_loader_writes_lake(tmp_path: Path) -> None:
    source_dir = tmp_path / "vendor"
    source_dir.mkdir()
    _make_csv(source_dir, "AAPL_NASDAQ", ["2024-01-02", "2024-01-03"])
    target_dir = tmp_path / "lake"
    loader = LocalDirectoryLoader(source_dir=source_dir, format="csv")
    result = loader.run(target_dir=target_dir)
    assert result["rows"] == 2
    assert "AAPL.NASDAQ" in result["symbols"]
    assert (target_dir / "bars").exists()
    assert any((target_dir / "bars").glob("*.parquet"))


def test_duckdb_extra_parquet_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from aqp.data.duckdb_engine import DuckDBHistoryProvider

    extra_dir = tmp_path / "extra" / "bars"
    extra_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "vt_symbol": "XYZ.LOCAL",
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.8, 9.9],
            "close": [10.1, 10.2],
            "volume": [100.0, 110.0],
        }
    ).to_parquet(extra_dir / "XYZ_LOCAL.parquet")

    provider = DuckDBHistoryProvider(
        parquet_dir=tmp_path / "empty",
        extra_parquet_paths=[tmp_path / "extra"],
    )
    from aqp.core.types import Exchange, Symbol

    bars = provider.get_bars(
        symbols=[Symbol(ticker="XYZ", exchange=Exchange.LOCAL)],
        start=datetime(2023, 1, 1),
        end=datetime(2025, 1, 1),
    )
    assert len(bars) == 2
