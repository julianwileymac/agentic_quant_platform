"""Tests for managed Alpha Vantage universe snapshot sync."""
from __future__ import annotations

import pandas as pd
import pytest


def _listing_frame(name_suffix: str = "") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "name": f"Apple{name_suffix}",
                "exchange": "NASDAQ",
                "assetType": "Stock",
                "ipoDate": "1980-12-12",
                "delistingDate": "",
                "status": "Active",
            },
            {
                "symbol": "MSFT",
                "name": f"Microsoft{name_suffix}",
                "exchange": "NASDAQ",
                "assetType": "Stock",
                "ipoDate": "1986-03-13",
                "delistingDate": "",
                "status": "Active",
            },
        ]
    )


class _FakeClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def listing_status(self, *, state: str = "active", date: str | None = None) -> pd.DataFrame:  # noqa: ARG002
        return self._frame.copy()


def test_sync_snapshot_upserts_and_lists(
    patched_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.data.sources.alpha_vantage import universe as universe_mod
    from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

    monkeypatch.setattr(universe_mod, "get_session", patched_db)
    monkeypatch.setattr(
        universe_mod,
        "register_dataset_version",
        lambda **kwargs: {"catalog_id": "catalog", "version_id": "version", "dataset_version": 1},  # noqa: ARG005
    )

    service = AlphaVantageUniverseService(client=_FakeClient(_listing_frame()))
    first = service.sync_snapshot(limit=10)
    assert first["ingested"] == 2
    assert first["created"] == 2
    assert first["updated"] == 0

    listed = service.list_snapshot(limit=10)
    tickers = {row["ticker"] for row in listed}
    assert {"AAPL", "MSFT"}.issubset(tickers)

    second_service = AlphaVantageUniverseService(client=_FakeClient(_listing_frame(" Inc")))
    second = second_service.sync_snapshot(limit=10)
    assert second["ingested"] == 2
    assert second["created"] == 0
    assert second["updated"] == 2
