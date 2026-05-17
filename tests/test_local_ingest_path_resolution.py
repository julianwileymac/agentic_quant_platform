"""Tests for host->container local ingest path resolution."""
from __future__ import annotations

from pathlib import Path

import pytest

from aqp.data.pipelines.local_paths import (
    LocalPathResolutionError,
    resolve_local_ingest_path,
)


def test_resolve_local_ingest_path_maps_windows_host_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aqp.config import settings

    container_root = tmp_path / "host-data"
    target = container_root / "sasdata" / "demo.csv"
    target.parent.mkdir(parents=True)
    target.write_text("col_a,col_b\n1,2\n", encoding="utf-8")

    monkeypatch.setattr(
        settings,
        "local_ingest_path_map",
        f"C:/Users/Julian Wiley/Data=>{container_root}",
        raising=False,
    )

    resolved = resolve_local_ingest_path(
        r"C:\Users\Julian Wiley\Data\sasdata\demo.csv",
        require_exists=True,
    )
    assert resolved == target.resolve()


def test_resolve_local_ingest_path_errors_when_unmapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.config import settings

    monkeypatch.setattr(settings, "local_ingest_path_map", "", raising=False)
    with pytest.raises(LocalPathResolutionError):
        resolve_local_ingest_path(
            r"C:\Users\Julian Wiley\Data\sasdata\missing.csv",
            require_exists=True,
        )
