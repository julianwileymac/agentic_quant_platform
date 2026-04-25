"""Tests for the persistent FeatureSet store."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.data.feature_sets import FeatureSetService, FeatureSetSpec


@pytest.fixture
def service(in_memory_db, tmp_path, monkeypatch) -> FeatureSetService:
    """Return a service backed by an in-memory SQLite session.

    Patches both the DB session and the on-disk cache root.
    """
    from aqp.data import feature_sets as fs_mod

    monkeypatch.setattr(fs_mod, "_cache_root", lambda: tmp_path / "feature_sets")
    (tmp_path / "feature_sets").mkdir(parents=True, exist_ok=True)
    return FeatureSetService()


def _bars(symbols: list[str], n: int = 60) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=n)
    rows = []
    rng = np.random.default_rng(3)
    for sym in symbols:
        prices = 100 + np.cumsum(rng.normal(0, 1, n))
        for i, ts in enumerate(dates):
            rows.append(
                {
                    "timestamp": ts,
                    "vt_symbol": sym,
                    "open": float(prices[i]),
                    "high": float(prices[i] + 0.5),
                    "low": float(prices[i] - 0.5),
                    "close": float(prices[i]),
                    "volume": 1_000_000.0,
                }
            )
    return pd.DataFrame(rows)


def test_create_get_update_archives(service: FeatureSetService) -> None:
    spec = FeatureSetSpec(
        name="test_panel",
        description="hello",
        kind="indicator",
        specs=["SMA:10", "RSI:14"],
        tags=["test"],
    )
    created = service.create(spec)
    assert created.id and created.version == 1
    fetched = service.get(created.id)
    assert fetched is not None
    assert fetched.name == "test_panel"
    by_name = service.get_by_name("test_panel")
    assert by_name is not None and by_name.id == created.id
    # update with new specs bumps version
    updated = service.update(
        created.id,
        FeatureSetSpec(
            name="ignored",
            description="updated",
            kind="indicator",
            specs=["SMA:10", "RSI:14", "MACD"],
            tags=["test"],
        ),
        notes="add macd",
    )
    assert updated.version == 2
    versions = service.versions(created.id)
    assert len(versions) >= 2
    # archive
    service.delete(created.id)
    again = service.list()
    assert all(r.id != created.id for r in again)


def test_materialize_uses_cache_on_second_call(
    service: FeatureSetService, tmp_path
) -> None:
    spec = FeatureSetSpec(
        name="bench_panel",
        kind="indicator",
        specs=["SMA:5", "RSI:7"],
    )
    created = service.create(spec)
    bars = _bars(["AAA.NYSE", "BBB.NYSE"])
    panel1 = service.materialize(created.id, bars)
    panel2 = service.materialize(created.id, bars)
    assert "sma_5" in panel1.columns
    assert "rsi_7" in panel1.columns
    assert len(panel1) == len(panel2)
    cache_dir = tmp_path / "feature_sets"
    assert cache_dir.exists()
    cache_files = list(cache_dir.glob("*.parquet"))
    assert cache_files, "expected at least one cached parquet"


def test_record_usage_visible_via_usages(service: FeatureSetService) -> None:
    spec = FeatureSetSpec(name="usage_panel", specs=["SMA:5"])
    created = service.create(spec)
    usage_id = service.record_usage(
        created.id,
        consumer_kind="backtest",
        consumer_id="bt-test",
        meta={"note": "first run"},
    )
    assert usage_id
    rows = service.usages(created.id)
    assert any(r.consumer_kind == "backtest" for r in rows)


def test_materialize_ad_hoc_does_not_persist(service: FeatureSetService) -> None:
    bars = _bars(["AAA.NYSE"])
    panel = service.materialize_ad_hoc(["SMA:5"], bars)
    assert "sma_5" in panel.columns
    # No FeatureSet row should exist.
    rows = service.list()
    assert all(r.name != "_preview" for r in rows)
