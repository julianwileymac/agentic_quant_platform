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
        **kwargs: Any,
    ) -> None:
        from aqp.config import settings

        url = f"https://api.tiingo.com{path if path.startswith('/') else '/' + path}"
        super().__init__(
            url=url,
            params=params,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {api_key or settings.tiingo_api_key}",
            }
            if (api_key or settings.tiingo_api_key)
            else None,
            chunk_rows=chunk_rows,
            **kwargs,
        )
