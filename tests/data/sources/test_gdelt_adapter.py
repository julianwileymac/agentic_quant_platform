"""GDelt manifest parsing + subject-filter + sink tests (no network)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from aqp.data.sources.gdelt.catalog import upsert_gdelt_mentions
from aqp.data.sources.gdelt.manifest import _parse_manifest
from aqp.data.sources.gdelt.parquet_sink import (
    derive_mentions,
    subject_filter_rows,
    write_partitioned,
)
from aqp.data.sources.gdelt.schema import GKG_COLUMNS, parse_tone, split_semicolon
from aqp.data.sources.gdelt.subject_filter import SubjectFilter
from aqp.persistence.models import Instrument


def test_parse_manifest_line():
    text = (
        "12345  d41d8cd98f00b204e9800998ecf8427e  "
        "http://data.gdeltproject.org/gkg/20240101000000.gkg.csv.zip\n"
        "67890  0123456789abcdef0123456789abcdef  "
        "http://data.gdeltproject.org/gkg/20240101001500.gkg.csv.zip\n"
    )
    entries = list(_parse_manifest(text))
    assert len(entries) == 2
    assert entries[0].timestamp == datetime(2024, 1, 1, 0, 0, 0)
    assert entries[1].timestamp == datetime(2024, 1, 1, 0, 15, 0)


def test_parse_tone():
    tone = parse_tone("1.23,4.56,2.11,5.67,0.5,0.25,123")
    assert tone["tone"] == 1.23
    assert tone["word_count"] == 123.0


def test_split_semicolon():
    assert split_semicolon("FOO;BAR; BAZ") == ["FOO", "BAR", "BAZ"]
    assert split_semicolon(None) == []


def _gkg_row(record_id: str, orgs: str, date: str = "20240101000000") -> dict:
    row = {col: "" for col in GKG_COLUMNS}
    row["gkg_record_id"] = record_id
    row["v21_date"] = datetime.strptime(date, "%Y%m%d%H%M%S")
    row["v2_enhanced_organizations"] = orgs
    row["v2_source_common_name"] = "example.com"
    row["v2_document_identifier"] = "https://example.com/story"
    row["v15_tone"] = "1.0,2.0,3.0,4.0,0.5,0.25,100"
    row["v2_enhanced_themes"] = "ECON_STOCKMARKET;BUS_EARNINGS"
    return row


def test_subject_filter_matches_registered_instrument(patched_db, sqlite_session_factory):
    with sqlite_session_factory() as session:
        session.add(
            Instrument(
                vt_symbol="AAPL.NASDAQ",
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="equity",
                security_type="equity",
                identifiers={"vt_symbol": "AAPL.NASDAQ", "ticker": "AAPL"},
                meta={"name": "Apple Inc."},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()

    subject_filter = SubjectFilter()
    assert subject_filter.load() > 0
    matches = subject_filter.match_organizations("Apple Inc.,40;Some Other Org,120")
    assert len(matches) == 1
    assert matches[0].ticker == "AAPL"


def test_subject_filter_rows_and_derive(patched_db, sqlite_session_factory):
    with sqlite_session_factory() as session:
        session.add(
            Instrument(
                vt_symbol="AAPL.NASDAQ",
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="equity",
                security_type="equity",
                identifiers={"ticker": "AAPL"},
                meta={"name": "Apple Inc."},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()
    df = pd.DataFrame(
        [
            _gkg_row("rec-1", "Apple Inc.,40;Some Other Org,120"),
            _gkg_row("rec-2", "Unrelated,10"),
        ]
    )
    subject_filter = SubjectFilter()
    filtered, report = subject_filter_rows(df, subject_filter)
    assert len(filtered) == 1
    assert filtered.iloc[0]["gkg_record_id"] == "rec-1"
    assert len(report) == 1

    mentions = derive_mentions(filtered, report)
    assert len(mentions) == 1
    assert mentions[0]["gkg_record_id"] == "rec-1"
    assert mentions[0]["tone"]["tone"] == 1.0

    persisted = upsert_gdelt_mentions(mentions)
    assert persisted == 1

    # Idempotent re-upsert — second call inserts zero new rows.
    again = upsert_gdelt_mentions(mentions)
    assert again == 0


def test_write_partitioned(tmp_path: Path):
    df = pd.DataFrame(
        [
            _gkg_row("rec-1", "Apple Inc.,40", date="20240101001500"),
            _gkg_row("rec-2", "Apple Inc.,40", date="20240102003000"),
        ]
    )
    out = write_partitioned(df, root=tmp_path)
    assert out is not None
    # Expect at least two date partitions created
    partitions = list(out.rglob("*.parquet"))
    assert len(partitions) >= 2
