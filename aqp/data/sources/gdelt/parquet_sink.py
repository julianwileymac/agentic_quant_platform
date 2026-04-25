"""Download a GDelt manifest entry, parse the CSV, write partitioned Parquet."""
from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from aqp.config import settings
from aqp.data.sources.gdelt.manifest import ManifestEntry
from aqp.data.sources.gdelt.schema import GKG_COLUMNS, parse_tone, split_semicolon
from aqp.data.sources.gdelt.subject_filter import SubjectFilter

logger = logging.getLogger(__name__)


class GDeltDownloadError(RuntimeError):
    """Raised when a manifest file fails to download or verify."""


def download_entry(
    entry: ManifestEntry,
    *,
    timeout: float = 120.0,
    verify_md5: bool = True,
) -> bytes:
    """Fetch the raw ``.zip`` blob for a manifest entry and verify its MD5."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(entry.url)
        resp.raise_for_status()
        content = resp.content
    if verify_md5 and entry.md5:
        actual = hashlib.md5(content).hexdigest()  # noqa: S324 - matches GDelt manifest
        if actual != entry.md5.lower():
            raise GDeltDownloadError(
                f"md5 mismatch for {entry.filename}: expected {entry.md5} got {actual}"
            )
    return content


def decode_zip(blob: bytes) -> pd.DataFrame:
    """Extract the single CSV from a GDelt zip and parse it as a DataFrame."""
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise GDeltDownloadError("zip did not contain a CSV")
        with zf.open(names[0]) as fh:
            df = pd.read_csv(
                fh,
                sep="\t",
                header=None,
                names=GKG_COLUMNS,
                dtype=str,
                encoding="utf-8",
                encoding_errors="replace",
                low_memory=False,
                on_bad_lines="skip",
            )
    if df.empty:
        return df
    df["v21_date"] = pd.to_datetime(df["v21_date"], format="%Y%m%d%H%M%S", errors="coerce")
    return df


def subject_filter_rows(
    df: pd.DataFrame,
    subject_filter: SubjectFilter,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Return only rows that match the subject filter plus a match report.

    The match report is a list of dicts ``{"instrument_id", "vt_symbol",
    "ticker", "matched_on", "source_value", "gkg_record_id"}`` suitable
    for upserting into the ``gdelt_mentions`` table.
    """
    if df.empty:
        return df, []
    subject_filter.load()
    matched_rows: list[int] = []
    report: list[dict[str, object]] = []
    for idx, row in df.iterrows():
        orgs = row.get("v2_enhanced_organizations") or row.get("v1_organizations")
        matches = subject_filter.match_organizations(orgs)
        if matches:
            matched_rows.append(idx)
            for match in matches:
                report.append(
                    {
                        "instrument_id": match.instrument_id,
                        "vt_symbol": match.vt_symbol,
                        "ticker": match.ticker,
                        "matched_on": match.matched_on,
                        "source_value": match.source_value,
                        "gkg_record_id": row.get("gkg_record_id"),
                    }
                )
    return df.loc[matched_rows].copy(), report


def write_partitioned(df: pd.DataFrame, *, root: Path | None = None) -> Path | None:
    """Write the GKG frame to a date-partitioned parquet dataset."""
    if df.empty:
        return None
    target_root = Path(root or (settings.parquet_dir / settings.gdelt_parquet_subdir))
    target_root.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    if "v21_date" in df.columns:
        dates = pd.to_datetime(df["v21_date"], errors="coerce")
    else:
        dates = pd.to_datetime(datetime.utcnow())
    df["_year"] = dates.dt.year.fillna(-1).astype(int)
    df["_month"] = dates.dt.month.fillna(-1).astype(int)
    df["_day"] = dates.dt.day.fillna(-1).astype(int)
    written = target_root
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(target_root),
        partition_cols=["_year", "_month", "_day"],
    )
    return written


def derive_mentions(
    df: pd.DataFrame,
    report: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return dicts ready to insert into ``gdelt_mentions``."""
    if not report:
        return []
    by_record: dict[str, list[dict[str, object]]] = {}
    for item in report:
        by_record.setdefault(str(item["gkg_record_id"]), []).append(item)

    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        record_id = row.get("gkg_record_id")
        if not record_id:
            continue
        matches = by_record.get(str(record_id))
        if not matches:
            continue
        tone = parse_tone(row.get("v15_tone"))
        themes = split_semicolon(
            row.get("v2_enhanced_themes") or row.get("v1_themes")
        )
        for match in matches:
            rows.append(
                {
                    "gkg_record_id": record_id,
                    "date": row.get("v21_date"),
                    "source_common_name": row.get("v2_source_common_name"),
                    "document_identifier": row.get("v2_document_identifier"),
                    "instrument_id": match["instrument_id"],
                    "themes": themes,
                    "tone": tone,
                    "organizations_match": [
                        {
                            "matched_on": match["matched_on"],
                            "source_value": match["source_value"],
                        }
                    ],
                }
            )
    return rows
