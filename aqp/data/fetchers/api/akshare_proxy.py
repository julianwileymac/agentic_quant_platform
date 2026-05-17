"""AKShare proxy fetcher.

Calls a single AKShare function by dotted name (``ak.stock_zh_a_hist``,
``ak.bond_zh_us_rate``, etc.) and returns the resulting pandas
DataFrame as Arrow batches. AKShare exposes hundreds of small
function-per-endpoint wrappers; the proxy makes them available as
manifest nodes without writing one fetcher per endpoint.

AKShare must be installed separately (``pip install akshare``); the
fetcher logs and short-circuits when it isn't.
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.akshare",
    display_name="AKShare (proxy)",
    kind=FetcherKind.API,
    description="Generic AKShare endpoint proxy. Specify function name + kwargs.",
    base_url="https://akshare.xyz",
    auth_type="none",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("market.bars.cn", "market.ratings.cn", "macro.cn", "futures.cn"),
)
class AkshareProxyFetcher(Fetcher):
    """Stream the result of one AKShare function as Arrow batches.

    ``function`` is a dotted attribute under the ``akshare`` package
    (e.g. ``stock_zh_a_hist``). ``kwargs`` are forwarded directly.
    """

    def __init__(
        self,
        *,
        function: str,
        kwargs: dict[str, Any] | None = None,
        chunk_rows: int = 50_000,
        **node_kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **node_kwargs)
        if not function:
            raise ValueError("AkshareProxyFetcher: function required")
        self.function = function
        self.callable_kwargs = dict(kwargs or {})
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"akshare://{self.function}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            ak = importlib.import_module("akshare")
        except Exception as exc:  # noqa: BLE001 - optional dep
            logger.warning("AkshareProxyFetcher unavailable: %s", exc)
            return

        fn = getattr(ak, self.function, None)
        if not callable(fn):
            logger.warning("akshare has no function %r", self.function)
            return

        ctx.emit("source", f"akshare {self.function}({list(self.callable_kwargs)})")
        df = fn(**self.callable_kwargs)
        if df is None or len(df) == 0:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)
