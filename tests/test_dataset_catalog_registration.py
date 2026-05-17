"""Tests for dataset catalog registration edge cases used by ingestion."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest


def test_register_empty_frame_without_summary_returns_empty(in_memory_db) -> None:
    from aqp.data.catalog import register_dataset_version

    out = register_dataset_version(
        name="bars.empty",
        provider="test",
        domain="market.bars",
        df=pd.DataFrame(),
    )
    assert out == {}


def test_register_summary_row_counts_persist(in_memory_db) -> None:
    from aqp.data.catalog import register_dataset_version

    out = register_dataset_version(
        name="bars.default",
        provider="alpha_vantage",
        domain="market.bars",
        df=None,
        summary_row_count=1000,
        summary_symbol_count=50,
        meta={"aggregated_run": True},
        frequency="1d",
    )
    assert out.get("dataset_version_id") is not None
    assert out.get("dataset_hash")


def test_ingest_skips_catalog_when_register_catalog_version_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.data import ingestion as ing

    calls: list[dict] = []
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "vt_symbol": ["AAPL.NASDAQ", "AAPL.NASDAQ"],
            "open": [1.0, 1.0],
            "high": [1.1, 1.1],
            "low": [0.9, 0.9],
            "close": [1.0, 1.0],
            "volume": [100.0, 100.0],
        }
    )
    fake_source = type("S", (), {"name": "test"})()

    monkeypatch.setattr(ing, "write_parquet", lambda df, parquet_dir=None, overwrite=False: Path("/tmp/test.parquet"))  # noqa: ARG005

    def _fake_fetch(
        resolved_source: object,
        *,
        symbols: list[str],
        start: object,
        end: object,
        interval: str,
        allow_fallback: bool = True,
    ) -> tuple[pd.DataFrame, object]:
        return (df, fake_source)

    monkeypatch.setattr(ing, "_fetch_with_fallback", _fake_fetch)
    monkeypatch.setattr("aqp.data.catalog.register_dataset_version", lambda **k: calls.append(k))

    out = ing.ingest(["AAPL.NASDAQ"], register_catalog_version=False)
    assert len(out) == 2
    assert calls == []


def test_register_dataset_version_uses_annotation_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.data import catalog as catalog_pkg
    from aqp.persistence.models import DatasetCatalog

    class _FakeResult:
        def __init__(self, one: object | None = None, scalar_value: int | None = None) -> None:
            self._one = one
            self._scalar_value = scalar_value

        def scalar_one_or_none(self) -> object | None:
            return self._one

        def scalar(self) -> int | None:
            return self._scalar_value

    class _FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []
            self._execute_calls = 0

        def execute(self, _stmt: object) -> _FakeResult:
            self._execute_calls += 1
            if self._execute_calls == 1:
                return _FakeResult(one=None)
            return _FakeResult(scalar_value=0)

        def add(self, obj: object) -> None:
            self.added.append(obj)

        def flush(self) -> None:
            for idx, obj in enumerate(self.added, start=1):
                if getattr(obj, "id", None) in (None, ""):
                    setattr(obj, "id", idx)

    fake_session = _FakeSession()

    @contextmanager
    def _fake_get_session():
        yield fake_session

    legacy_catalog = catalog_pkg._legacy_catalog
    monkeypatch.setattr(legacy_catalog, "get_session", _fake_get_session)

    catalog_pkg.register_dataset_version(
        name="aqp_test.description_case",
        provider="iceberg",
        domain="user.dataset",
        df=pd.DataFrame({"col_a": [1]}),
        iceberg_identifier="aqp_test.description_case",
        llm_annotations={"description": "Annotated from LLM"},
    )
    catalog_row = next(obj for obj in fake_session.added if isinstance(obj, DatasetCatalog))
    assert catalog_row.description == "Annotated from LLM"


def test_discovery_service_falls_back_to_llm_annotation_description() -> None:
    from aqp.data.discovery.service import DiscoveryService
    from aqp.persistence.models import DatasetCatalog

    row = DatasetCatalog(
        id=123,
        name="llm-only-description",
        provider="self_service",
        domain="user.dataset",
        description=None,
        llm_annotations={"description": "Fallback from llm_annotations"},
        dataset_kind="external",
        is_ingested=False,
        external_spec_json={"intent_kind": "external"},
    )
    entry = DiscoveryService()._row_to_entry(row)
    assert entry.description == "Fallback from llm_annotations"
