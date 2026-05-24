"""Quandl / Nasdaq Data Link fetcher."""
from __future__ import annotations

from typing import Any

from aqp.data.fetchers.api.rest_api import RestApiFetcher
from aqp.data.fetchers.base import (
    FetcherCapability,
    FetcherKind,
    RateLimit,
    register_source_fetcher,
)


@register_source_fetcher(
    "source.quandl",
    display_name="Nasdaq Data Link (Quandl)",
    kind=FetcherKind.API,
    description="Fetch a Nasdaq Data Link / Quandl dataset endpoint.",
    base_url="https://data.nasdaq.com/api/v3",
    auth_type="api_key",
    credentials_ref="AQP_QUANDL_API_KEY",
    rate_limit=RateLimit(requests_per_minute=20),
    capabilities=(FetcherCapability.REQUIRES_AUTH.value,),
    domains=("economic.series", "fundamentals.statements"),
)
class QuandlFetcher(RestApiFetcher):
    """Quandl / Nasdaq Data Link REST fetcher.

    ``dataset`` is shaped ``DATABASE_CODE/DATASET_CODE`` (e.g.
    ``WIKI/AAPL``). ``return_format`` defaults to ``json``.
    """

    default_rate_limit = RateLimit(requests_per_minute=20)

    def __init__(
        self,
        *,
        dataset: str,
        return_format: str = "json",
        params: dict[str, Any] | None = None,
        api_key: str | None = None,
        chunk_rows: int = 5_000,
        credential_label: str = "primary",
        **kwargs: Any,
    ) -> None:
        from aqp.data.fetchers.api._resolver import resolve_vendor_api_key

        url = f"https://data.nasdaq.com/api/v3/datasets/{dataset}.{return_format}"
        # Rule 26 compliant: resolve via CredentialResolver +
        # BrokerCredentialStore first, fall back to legacy settings.
        api_key_value = api_key or resolve_vendor_api_key(
            provider="quandl",
            label=credential_label,
            settings_attr="quandl_api_key",
        )
        super().__init__(
            url=url,
            params=params,
            api_key_param="api_key",
            api_key_value=api_key_value or None,
            record_path=["dataset_data", "data"],
            chunk_rows=chunk_rows,
            **kwargs,
        )
