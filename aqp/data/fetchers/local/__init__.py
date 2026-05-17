"""Local-disk fetchers: file, directory, database."""
from __future__ import annotations

from aqp.data.fetchers.local.database_fetcher import DatabaseFetcher
from aqp.data.fetchers.local.directory_fetcher import DirectoryFetcher
from aqp.data.fetchers.local.file_fetcher import FileFetcher

__all__ = [
    "DatabaseFetcher",
    "DirectoryFetcher",
    "FileFetcher",
]
