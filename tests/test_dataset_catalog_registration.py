"""Tests for dataset catalog registration edge cases used by ingestion."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def test_register_empty_frame_without_summary_returns_empty(in_memory_db) -> None:
    from aqp.data.catalog import register_dataset_version

    out = register_dataset_version(
        name="bars.empty",
        provider="test",
        domain="market.bars",
        df=pd.DataFrame(),
    )
    assert out == {}


def test_register_summary_row_counts_persist(in_memory_db) -> None:
    from aqp.data.catalog import register_dataset_version

    out = register_dataset_version(
        name="bars.default",
        provider="alpha_vantage",
        domain="market.bars",
        df=None,
        summary_row_count=1000,
        summary_symbol_count=50,
        meta={"aggregated_run": True},
        frequency="1d",
    )
    assert out.get("dataset_version_id") is not None
    assert out.get("dataset_hash")


def test_ingest_skips_catalog_when_register_catalog_version_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.data import ingestion as ing

    calls: list[dict] = []
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "vt_symbol": ["AAPL.NASDAQ", "AAPL.NASDAQ"],
            "open": [1.0, 1.0],
            "high": [1.1, 1.1],
            "low": [0.9, 0.9],
            "close": [1.0, 1.0],
            "volume": [100.0, 100.0],
        }
    )
    fake_source = type("S", (), {"name": "test"})()

    monkeypatch.setattr(ing, "write_parquet", lambda df, parquet_dir=None, overwrite=False: Path("/tmp/test.parquet"))  # noqa: ARG005

    def _fake_fetch(
        resolved_source: object,
        *,
        symbols: list[str],
        start: object,
        end: object,
        interval: str,
        allow_fallback: bool = True,
    ) -> tuple[pd.DataFrame, object]:
        return (df, fake_source)

    monkeypatch.setattr(ing, "_fetch_with_fallback", _fake_fetch)
    monkeypatch.setattr("aqp.data.catalog.register_dataset_version", lambda **k: calls.append(k))

    out = ing.ingest(["AAPL.NASDAQ"], register_catalog_version=False)
    assert len(out) == 2
    assert calls == []
