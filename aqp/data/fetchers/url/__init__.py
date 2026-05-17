"""URL-based fetchers (HTTP, S3, GCS, Azure, archives)."""
from __future__ import annotations

from aqp.data.fetchers.url.archive_fetcher import ArchiveFetcher
from aqp.data.fetchers.url.azure_blob_fetcher import AzureBlobFetcher
from aqp.data.fetchers.url.gcs_fetcher import GcsFetcher
from aqp.data.fetchers.url.http_fetcher import HttpFetcher
from aqp.data.fetchers.url.s3_fetcher import S3Fetcher

__all__ = [
    "ArchiveFetcher",
    "AzureBlobFetcher",
    "GcsFetcher",
    "HttpFetcher",
    "S3Fetcher",
]
