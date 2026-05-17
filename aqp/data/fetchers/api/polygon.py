"""Polygon.io fetcher."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.api.rest_api import RestApiFetcher
from aqp.data.fetchers.base import (
    FetcherCapability,
    FetcherKind,
    Pagination,
    RateLimit,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.polygon",
    display_name="Polygon.io",
    kind=FetcherKind.API,
    description="Fetch a Polygon.io REST endpoint with auto pagination.",
    base_url="https://api.polygon.io",
    auth_type="api_key",
    credentials_ref="AQP_POLYGON_API_KEY",
    rate_limit=RateLimit(requests_per_minute=5),
    capabilities=(
        FetcherCapability.SUPPORTS_PAGINATION.value,
        FetcherCapability.REQUIRES_AUTH.value,
    ),
    domains=("market.bars", "market.quotes", "market.ticks"),
)
class PolygonFetcher(RestApiFetcher):
    """Polygon.io REST fetcher.

    ``path`` is appended to ``https://api.polygon.io`` (e.g.
    ``/v2/aggs/ticker/AAPL/range/1/day/2024-01-01/2024-01-31``). The
    Polygon API returns ``{ "results": [...], "next_url": "..." }``;
    the next-link pagination handles continuation.
    """

    default_rate_limit = RateLimit(requests_per_minute=5)

    def __init__(
        self,
        *,
        path: str,
        params: dict[str, Any] | None = None,
        api_key: str | None = None,
        max_pages: int = 10,
        chunk_rows: int = 5_000,
        **kwargs: Any,
    ) -> None:
        from aqp.config import settings

        url = f"https://api.polygon.io{path if path.startswith('/') else '/' + path}"
        api_key_value = api_key or settings.polygon_api_key
        super().__init__(
            url=url,
            params=params,
            api_key_param="apiKey",
            api_key_value=api_key_value or None,
            pagination=Pagination(
                next_link_field="next_url",
                max_pages=max_pages,
            ),
            record_path=["results"],
            chunk_rows=chunk_rows,
            **kwargs,
        )
