"""FRED adapter tests — uses a stub client so no network is touched."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from aqp.data.sources.base import ObservationsResult, ProbeResult
from aqp.data.sources.fred.series import FredSeriesAdapter


class _StubFredClient:
    """Minimal stand-in for :class:`FredClient`."""

    def __init__(
        self,
        *,
        probe_ok: bool = True,
        observations: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.probe_ok = probe_ok
        self._observations = observations or [
            {
                "date": "2024-01-01",
                "value": "3.95",
                "realtime_start": "2024-01-01",
                "realtime_end": "2024-12-31",
            },
            {
                "date": "2024-01-02",
                "value": "3.97",
                "realtime_start": "2024-01-02",
                "realtime_end": "2024-12-31",
            },
            {
                "date": "2024-01-03",
                "value": ".",  # GDelt-style missing observation
                "realtime_start": "2024-01-03",
                "realtime_end": "2024-12-31",
            },
        ]
        self._metadata = metadata or {
            "id": "DGS10",
            "title": "10-Year Treasury Constant Maturity Rate",
            "units": "Percent",
            "units_short": "%",
            "frequency": "Daily",
            "frequency_short": "D",
            "seasonal_adjustment": "Not Seasonally Adjusted",
            "seasonal_adjustment_short": "NSA",
            "popularity": 80,
            "observation_start": "1962-01-02",
            "observation_end": "2024-04-23",
            "last_updated": "2024-04-23 16:02:04-05",
            "notes": "Board of Governors of the Federal Reserve System.",
        }

    def probe(self):
        return (True, "ok") if self.probe_ok else (False, "no api key")

    def get_series(self, series_id: str) -> dict[str, Any] | None:
        if series_id == self._metadata.get("id"):
            return dict(self._metadata)
        return None

    def get_observations(
        self,
        series_id: str,
        *,
        observation_start: str | None = None,
        observation_end: str | None = None,
        **_: Any,
    ):
        return list(self._observations)

    def search_series(self, query: str, *, limit: int = 25, **_: Any):
        return [dict(self._metadata)]


def test_fred_adapter_probe_ok(patched_db, tmp_path: Path):
    adapter = FredSeriesAdapter(
        client=_StubFredClient(probe_ok=True),
        parquet_root=tmp_path,
    )
    result = adapter.probe()
    assert isinstance(result, ProbeResult)
    assert result.ok


def test_fred_adapter_probe_fail(patched_db, tmp_path: Path):
    adapter = FredSeriesAdapter(
        client=_StubFredClient(probe_ok=False),
        parquet_root=tmp_path,
    )
    result = adapter.probe()
    assert not result.ok


def test_fred_adapter_fetch_observations_persists(patched_db, tmp_path: Path):
    adapter = FredSeriesAdapter(
        client=_StubFredClient(),
        parquet_root=tmp_path,
    )
    result = adapter.fetch_observations(series_id="DGS10", start="2024-01-01")
    assert isinstance(result, ObservationsResult)
    assert not result.empty
    assert result.row_count == 2  # missing "." row is dropped
    # Parquet was written
    files = list(tmp_path.glob("*.parquet"))
    assert any(f.name == "DGS10.parquet" for f in files)
    # Lineage is emitted (best-effort — may be empty if the catalog fails)
    assert isinstance(result.lineage, dict)

    # FredSeries row persisted
    from aqp.persistence.models import FredSeries
    from sqlalchemy import select

    from aqp.persistence.db import get_session

    with get_session() as session:
        row = session.execute(
            select(FredSeries).where(FredSeries.series_id == "DGS10")
        ).scalar_one()
        assert row.title.startswith("10-Year")


def test_fred_adapter_fetch_metadata_search(patched_db, tmp_path: Path):
    adapter = FredSeriesAdapter(
        client=_StubFredClient(),
        parquet_root=tmp_path,
    )
    # single series
    payload = adapter.fetch_metadata(series_id="DGS10")
    assert payload["found"] is True
    # search
    payload = adapter.fetch_metadata(query="inflation")
    assert payload["count"] == 1
