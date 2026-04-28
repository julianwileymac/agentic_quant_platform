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
    monkeypatch.setattr(
        AlphaVantageUniverseService,
        "_sync_identifier_links",
        lambda self_inner, normalized: int(len(normalized)) * 3,
    )

    service = AlphaVantageUniverseService(client=_FakeClient(_listing_frame()))
    first = service.sync_snapshot(limit=10)
    assert first["ingested"] == 2
    assert first["created"] == 2
    assert first["updated"] == 0
    assert first["identifier_links"] == 6

    listed = service.list_snapshot(limit=10)
    tickers = {row["ticker"] for row in listed}
    assert {"AAPL", "MSFT"}.issubset(tickers)

    second_service = AlphaVantageUniverseService(client=_FakeClient(_listing_frame(" Inc")))
    second = second_service.sync_snapshot(limit=10)
    assert second["ingested"] == 2
    assert second["created"] == 0
    assert second["updated"] == 2
    assert second["identifier_links"] == 6


def test_sync_identifier_links_emits_three_schemes_per_row(monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

    captured = {}

    class _FakeResolver:
        def __init__(self, source_name=None):  # noqa: ARG002
            captured["source"] = source_name
            captured["specs"] = []

        def upsert_links(self, specs):
            captured["specs"].extend(list(specs))
            return [f"link-{idx}" for idx in range(len(captured["specs"]))]

    import aqp.data.sources.resolvers.identifiers as resolver_mod

    monkeypatch.setattr(resolver_mod, "IdentifierResolver", _FakeResolver)

    df = pd.DataFrame(
        [
            {"vt_symbol": "AAPL.NASDAQ", "ticker": "AAPL", "name": "Apple", "exchange": "NASDAQ", "asset_type": "Stock", "status": "Active"},
        ]
    )
    service = AlphaVantageUniverseService(client=_FakeClient(_listing_frame()))
    count = service._sync_identifier_links(df)
    schemes = sorted({spec.scheme for spec in captured["specs"]})
    assert count == 3
    assert schemes == ["alpha_vantage_symbol", "ticker", "vt_symbol"]
    assert captured["source"] == "alpha_vantage"
