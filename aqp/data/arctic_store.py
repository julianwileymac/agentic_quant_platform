"""ArcticDB tick-data store (optional).

If ``arcticdb`` isn't installed, the class gracefully stubs out with
``NotImplementedError``. Install with ``pip install agentic-quant-platform[arcticdb]``.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)


class ArcticStore:
    def __init__(self, uri: str | None = None, library: str = "ticks") -> None:
        self.uri = uri or settings.arctic_uri
        self.library = library
        self._store: Any | None = None
        self._lib: Any | None = None

    def _connect(self):
        if self._store is not None:
            return
        try:
            from arcticdb import Arctic
        except ImportError as e:  # pragma: no cover
            raise NotImplementedError(
                "arcticdb is not installed. Install with `pip install arcticdb`."
            ) from e
        self._store = Arctic(self.uri)
        if self.library not in self._store.list_libraries():
            self._store.create_library(self.library)
        self._lib = self._store[self.library]

    def write(self, symbol_key: str, frame: pd.DataFrame) -> None:
        self._connect()
        assert self._lib is not None
        self._lib.write(symbol_key, frame)
        logger.info("ArcticDB: wrote %d rows to %s", len(frame), symbol_key)

    def read(
        self, symbol_key: str, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None
    ) -> pd.DataFrame:
        self._connect()
        assert self._lib is not None
        q = None
        if start is not None or end is not None:
            from arcticdb import QueryBuilder

            q = QueryBuilder()
            if start is not None:
                q = q[q["timestamp"] >= start]
            if end is not None:
                q = q[q["timestamp"] <= end]
        return self._lib.read(symbol_key, query_builder=q).data

    def list_symbols(self) -> list[str]:
        self._connect()
        assert self._lib is not None
        return self._lib.list_symbols()
