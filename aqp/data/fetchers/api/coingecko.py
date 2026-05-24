"""CoinGecko fetcher (crypto market data)."""
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
    "source.coingecko",
    display_name="CoinGecko",
    kind=FetcherKind.API,
    description="Fetch CoinGecko crypto market endpoints.",
    base_url="https://api.coingecko.com/api/v3",
    auth_type="optional_api_key",
    credentials_ref="AQP_COINGECKO_API_KEY",
    rate_limit=RateLimit(requests_per_minute=50),
    capabilities=(FetcherCapability.SUPPORTS_PAGINATION.value,),
    domains=("crypto.market", "crypto.history"),
)
class CoingeckoFetcher(RestApiFetcher):
    """CoinGecko REST fetcher.

    ``path`` is appended to ``https://api.coingecko.com/api/v3``.
    Pro tier users may pass ``api_key=`` to enable the authenticated
    endpoint at ``api.coingecko.com``.
    """

    default_rate_limit = RateLimit(requests_per_minute=50)

    def __init__(
        self,
        *,
        path: str,
        params: dict[str, Any] | None = None,
        api_key: str | None = None,
        chunk_rows: int = 1_000,
        credential_label: str = "primary",
        **kwargs: Any,
    ) -> None:
        from aqp.data.fetchers.api._resolver import resolve_vendor_api_key

        url = f"https://api.coingecko.com/api/v3{path if path.startswith('/') else '/' + path}"
        headers: dict[str, str] = {}
        token = api_key or resolve_vendor_api_key(
            provider="coingecko",
            label=credential_label,
            settings_attr="coingecko_api_key",
        )
        if token:
            headers["x-cg-pro-api-key"] = token
        super().__init__(
            url=url,
            params=params,
            headers=headers,
            chunk_rows=chunk_rows,
            **kwargs,
        )
