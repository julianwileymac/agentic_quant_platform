from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_alpha_vantage_health_route_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.routes.alpha_vantage import health
    from aqp.services.alpha_vantage_service import AlphaVantageService

    service = AlphaVantageService()
    monkeypatch.setattr(service.settings, "alpha_vantage_api_key", "")
    monkeypatch.setattr(service.settings, "alpha_vantage_api_key_file", "")

    payload = await health(service)
    assert payload.enabled is True
    assert payload.credentials_loaded is False


def test_bulk_request_defaults() -> None:
    from aqp.api.routes.alpha_vantage import BulkLoadRequest

    payload = BulkLoadRequest(category="timeseries", symbols=["IBM"])
    assert payload.category == "timeseries"
    assert payload.extra_params == {}


@pytest.mark.asyncio
async def test_functions_catalog_exposes_lake_supported_history() -> None:
    from aqp.api.routes.alpha_vantage import functions_catalog

    payload = await functions_catalog()
    ids = {entry["id"] for entry in payload.functions}
    assert "timeseries.daily_adjusted" in ids
    assert any(entry["lake_supported"] for entry in payload.functions)


@pytest.mark.asyncio
async def test_timeseries_route_forwards_cache_controls() -> None:
    from aqp.api.routes.alpha_vantage import timeseries

    class _Service:
        enabled = True

        async def timeseries(self, function: str, **params):
            return {"function": function, "params": params}

    payload = await timeseries(
        "daily",
        symbol="IBM",
        cache=False,
        cache_ttl=12,
        service=_Service(),
    )
    assert payload["params"]["cache"] is False
    assert payload["params"]["cache_ttl"] == 12
