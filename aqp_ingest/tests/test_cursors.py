"""Hermetic tests for the PointInTimeIncrementalCursor.

Pins the survivorship-bias-free resume contract that the
financial connectors rely on for partitioned backfills.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from aqp_ingest_cdk.cursors import PointInTimeIncrementalCursor


def test_update_only_advances():
    cur = PointInTimeIncrementalCursor(cursor_field="t")
    cur.update("AAPL", "2024-01-01")
    cur.update("AAPL", "2023-12-01")  # earlier — must not regress
    assert cur.latest("AAPL") == "2024-01-01"
    cur.update("AAPL", "2024-02-01")
    assert cur.latest("AAPL") == "2024-02-01"


def test_iter_partitions_resumes_per_key():
    cur = PointInTimeIncrementalCursor(cursor_field="t")
    cur.update("AAPL", datetime(2024, 1, 5).isoformat())

    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 8)
    slices = list(
        cur.iter_partitions(
            keys=["AAPL", "MSFT"],
            start=start,
            end=end,
            step_days=1,
        )
    )
    aapl_slices = [s for s in slices if s["key"] == "AAPL"]
    msft_slices = [s for s in slices if s["key"] == "MSFT"]
    # AAPL resumes from 2024-01-05; MSFT starts at 2024-01-01.
    assert aapl_slices[0]["from"] == "2024-01-05"
    assert msft_slices[0]["from"] == "2024-01-01"


def test_from_state_round_trip():
    state = {"AAPL": "2024-01-05T00:00:00", "MSFT": "2024-02-01T00:00:00"}
    cur = PointInTimeIncrementalCursor.from_state("t", state)
    assert cur.latest("AAPL") == "2024-01-05T00:00:00"
    assert cur.latest("MSFT") == "2024-02-01T00:00:00"
    round_trip = cur.to_state()
    assert round_trip == state


def test_merge_advances_each_key():
    cur = PointInTimeIncrementalCursor(cursor_field="t")
    cur.merge({"AAPL": "2024-01-01"})
    cur.merge({"AAPL": "2024-02-01", "MSFT": "2024-01-15"})
    assert cur.latest("AAPL") == "2024-02-01"
    assert cur.latest("MSFT") == "2024-01-15"


def test_iter_partitions_skips_when_cursor_past_end():
    cur = PointInTimeIncrementalCursor(cursor_field="t")
    cur.update("AAPL", datetime(2030, 1, 1).isoformat())
    out = list(
        cur.iter_partitions(
            keys=["AAPL"],
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 8),
            step_days=1,
        )
    )
    assert out == []


def test_partition_step_respects_step_days():
    cur = PointInTimeIncrementalCursor(cursor_field="t")
    start = datetime(2024, 1, 1)
    end = start + timedelta(days=14)
    out = list(
        cur.iter_partitions(
            keys=["AAPL"],
            start=start,
            end=end,
            step_days=7,
        )
    )
    assert len(out) == 2
    assert out[0]["from"] == "2024-01-01"
    assert out[0]["to"] == "2024-01-08"
    assert out[1]["from"] == "2024-01-08"
    assert out[1]["to"] == "2024-01-15"
