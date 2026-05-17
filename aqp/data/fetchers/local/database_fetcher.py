"""Stream rows from a SQLAlchemy URL as Arrow batches."""
from __future__ import annotations

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
    "source.database",
    display_name="SQL Database",
    kind=FetcherKind.DATABASE,
    description="Stream a SQL query as Arrow batches via SQLAlchemy + pandas chunked read.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("database.table", "database.query"),
    auth_type="connection_string",
)
class DatabaseFetcher(Fetcher):
    """Run ``query`` against ``url`` and yield Arrow batches.

    Either ``query`` or ``table`` must be provided. ``params`` are
    bound to the query as :class:`dict`; SQLAlchemy 2-style positional
    parameters are not supported here.
    """

    def __init__(
        self,
        *,
        url: str,
        query: str | None = None,
        table: str | None = None,
        params: dict[str, Any] | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if not query and not table:
            raise ValueError("DatabaseFetcher requires either query or table")
        self.url = url
        self.query = query
        self.table = table
        self.params = dict(params or {})
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        # Avoid leaking credentials.
        try:
            from sqlalchemy.engine.url import make_url

            url = make_url(self.url)
            return str(url.set(password="***"))
        except Exception:
            return self.url

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        import pandas as pd
        import pyarrow as pa
        from sqlalchemy import create_engine, text

        engine = create_engine(self.url)
        sql = self.query or f"SELECT * FROM {self.table}"
        with engine.connect() as conn:
            result = pd.read_sql_query(
                text(sql),
                conn,
                params=self.params,
                chunksize=self.chunk_rows,
            )
            for chunk in result:
                if chunk is None or len(chunk) == 0:
                    continue
                table = pa.Table.from_pandas(chunk, preserve_index=False)
                yield from table.to_batches()
