"""DuckDB-backed store for batch-ingested news items.

Persistence shape::

    {settings.parquet_dir}/news/{vt_symbol}.parquet
    columns: id, title, source, url, published_at, summary, sentiment

The :class:`NewsStore` is optional — the trader crew's ``news_tool``
calls the live provider on every propagate, which is fine for adhoc
runs. Use the store when you want to cache ingests for repeated
backtests or to run sentiment scoring offline.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)


class NewsStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else (settings.parquet_dir / "news")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, vt_symbol: str) -> Path:
        safe = vt_symbol.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.parquet"

    def upsert(self, vt_symbol: str, items: list[dict]) -> Path:
        """Merge ``items`` into the symbol's Parquet file, dedup-ing on ``id``."""
        path = self._path(vt_symbol)
        new_df = pd.DataFrame(items)
        if new_df.empty:
            return path
        if path.exists():
            try:
                old_df = pd.read_parquet(path)
            except Exception:
                old_df = pd.DataFrame()
            combined = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined = new_df
        if "id" in combined.columns:
            combined = combined.drop_duplicates(subset=["id"], keep="last")
        combined.to_parquet(path, index=False)
        return path

    def fetch(
        self,
        vt_symbol: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Return cached items as a DataFrame."""
        path = self._path(vt_symbol)
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(path)
        if df.empty:
            return df
        if "published_at" in df.columns:
            try:
                df["published_at_dt"] = pd.to_datetime(df["published_at"], errors="coerce")
            except Exception:
                df["published_at_dt"] = pd.NaT
            if since is not None:
                df = df[df["published_at_dt"] >= pd.Timestamp(since)]
            if until is not None:
                df = df[df["published_at_dt"] <= pd.Timestamp(until)]
            df = df.sort_values("published_at_dt", ascending=False)
        if limit:
            df = df.head(int(limit))
        return df.reset_index(drop=True)
