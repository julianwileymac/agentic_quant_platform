"""Parquet-aware discovery/extraction regression tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from aqp.data.pipelines.discovery import discover_datasets
from aqp.data.pipelines.extractors import MemberRef, iter_member_chunks


def _write_csv(path: Path) -> None:
    pd.DataFrame(
        {
            "id": [1, 2, 3],
            "value": [10.0, 11.0, 12.0],
        }
    ).to_csv(path, index=False)


def _write_parquet(path: Path) -> None:
    pd.DataFrame(
        {
            "id": [1, 2, 3],
            "value": [10.0, 11.0, 12.0],
        }
    ).to_parquet(path, index=False)


def test_discovery_prefers_parquet_over_csv_for_same_stem(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    parquet_path = tmp_path / "prices.parquet"
    _write_csv(csv_path)
    _write_parquet(parquet_path)

    datasets = [ds for ds in discover_datasets(tmp_path) if ds.family != "__assets__"]
    assert len(datasets) == 1
    dataset = datasets[0]
    assert dataset.family == "prices"
    assert dataset.file_count == 1
    assert dataset.members[0].format == "parquet"
    assert any(
        "duplicate-format-priority-suppressed"
        in str(item.get("reason", ""))
        for item in dataset.inventory_extra
    )
    assert "id" in dataset.sample_columns
    assert "value" in dataset.sample_columns


def test_iter_member_chunks_reads_parquet(tmp_path: Path) -> None:
    parquet_path = tmp_path / "prices.parquet"
    _write_parquet(parquet_path)
    member = MemberRef(
        path=str(parquet_path),
        archive_path=None,
        format="parquet",
        delimiter=None,
    )
    chunks = list(iter_member_chunks(member, chunk_rows=2))
    assert chunks
    assert sum(chunk.num_rows for chunk in chunks) == 3
    assert "id" in chunks[0].column_names
    assert "value" in chunks[0].column_names
