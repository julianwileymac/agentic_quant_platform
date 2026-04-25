"""Minimal manifest parser for http://data.gdeltproject.org/gkg/index.html.

The manifest is a plain text file with one line per 15-minute archive::

    <size_bytes>  <md5>  <url>

This module fetches (and caches) the manifest, then returns a list of
:class:`ManifestEntry` objects filtered by a date window so the
ingester only has to download the slices the user actually asked for.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


_DATETIME_RE = re.compile(r"/(?P<ts>\d{14})\.gkg\.csv\.zip$")
_LINE_RE = re.compile(r"^\s*(?P<size>\d+)\s+(?P<md5>[a-f0-9]{32})\s+(?P<url>\S+)", re.IGNORECASE)


@dataclass(frozen=True)
class ManifestEntry:
    url: str
    size: int
    md5: str
    timestamp: datetime

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


class GDeltManifest:
    """Fetch + filter the GKG manifest."""

    def __init__(
        self,
        *,
        manifest_url: str | None = None,
        cache_dir: Path | str | None = None,
        cache_ttl_seconds: int = 3600,
        timeout: float = 60.0,
    ) -> None:
        self.manifest_url = manifest_url or settings.gdelt_manifest_url
        self.cache_dir = Path(cache_dir) if cache_dir else settings.data_dir / "gdelt_cache"
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Fetch / cache
    # ------------------------------------------------------------------

    def fetch_manifest(self, *, force_refresh: bool = False) -> str:
        """Return the raw manifest text, caching it on disk."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / "gkg_manifest.txt"
        if (
            not force_refresh
            and cache_path.exists()
            and (
                datetime.utcnow()
                - datetime.utcfromtimestamp(cache_path.stat().st_mtime)
            ).total_seconds()
            < self.cache_ttl_seconds
        ):
            return cache_path.read_text(encoding="utf-8", errors="replace")
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(self.manifest_url)
            resp.raise_for_status()
            text = resp.text
        cache_path.write_text(text, encoding="utf-8")
        return text

    def entries(self, *, force_refresh: bool = False) -> list[ManifestEntry]:
        """Parse the cached manifest into :class:`ManifestEntry` objects."""
        text = self.fetch_manifest(force_refresh=force_refresh)
        return list(_parse_manifest(text))

    # ------------------------------------------------------------------
    # Windowing
    # ------------------------------------------------------------------

    def list_window(
        self,
        start: datetime | str,
        end: datetime | str,
        *,
        force_refresh: bool = False,
    ) -> list[ManifestEntry]:
        """Return manifest entries with ``start <= timestamp <= end``."""
        start_dt = _coerce_dt(start)
        end_dt = _coerce_dt(end)
        if end_dt < start_dt:
            raise ValueError("GDelt manifest window: end < start")
        entries = self.entries(force_refresh=force_refresh)
        return [e for e in entries if start_dt <= e.timestamp <= end_dt]

    def list_last_hours(self, hours: int = 24) -> list[ManifestEntry]:
        """Return entries covering the last ``hours`` hours."""
        end = datetime.utcnow()
        return self.list_window(end - timedelta(hours=hours), end)


def _parse_manifest(text: str) -> Iterable[ManifestEntry]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _LINE_RE.match(line)
        if not match:
            logger.debug("gdelt manifest: skipping unparsable line %s", line[:80])
            continue
        url = match.group("url")
        ts_match = _DATETIME_RE.search(url)
        if not ts_match:
            continue
        try:
            timestamp = datetime.strptime(ts_match.group("ts"), "%Y%m%d%H%M%S")
        except ValueError:
            continue
        try:
            size = int(match.group("size"))
        except ValueError:
            continue
        yield ManifestEntry(
            url=url,
            size=size,
            md5=match.group("md5").lower(),
            timestamp=timestamp,
        )


def _coerce_dt(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        import pandas as pd

        return pd.Timestamp(value).to_pydatetime()
