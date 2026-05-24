"""Tiingo fetcher (daily prices, fundamentals, news)."""
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
    "source.tiingo",
    display_name="Tiingo",
    kind=FetcherKind.API,
    description="Fetch a Tiingo REST endpoint (prices, news, fundamentals).",
    base_url="https://api.tiingo.com",
    auth_type="api_key",
    credentials_ref="AQP_TIINGO_API_KEY",
    rate_limit=RateLimit(requests_per_minute=60),
    capabilities=(
        FetcherCapability.REQUIRES_AUTH.value,
    ),
    domains=("market.bars", "fundamentals.statements", "news"),
)
class TiingoFetcher(RestApiFetcher):
    """Tiingo REST fetcher; ``path`` is appended to the base URL."""

    default_rate_limit = RateLimit(requests_per_minute=60)

    def __init__(
        self,
        *,
        path: str,
        params: dict[str, Any] | None = None,
        api_key: str | None = None,
        chunk_rows: int = 5_000,
        credential_label: str = "primary",
        **kwargs: Any,
    ) -> None:
        from aqp.data.fetchers.api._resolver import resolve_vendor_api_key

        url = f"https://api.tiingo.com{path if path.startswith('/') else '/' + path}"
        # Rule 26: resolve via CredentialResolver first.
        resolved = api_key or resolve_vendor_api_key(
            provider="tiingo",
            label=credential_label,
            settings_attr="tiingo_api_key",
        )
        super().__init__(
            url=url,
            params=params,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {resolved}",
            }
            if resolved
            else None,
            chunk_rows=chunk_rows,
            **kwargs,
        )
