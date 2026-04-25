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
