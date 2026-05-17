from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
import pyarrow as pa
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from aqp.data.catalog.active_metadata import BusinessMetadata
from aqp.data.engine.nodes import NodeContext
from aqp.data.fabric.schema_registry import OHLCVSchema, SchemaValidationError
from aqp.data.fetchers.base import Fetcher
from aqp.data.fetchers.fabric_mixin import FabricFetcherMixin
from aqp.persistence.models import Base
from aqp.persistence.models_ingestion_ledger import IngestionLedgerRow


class _TestFetcher(Fetcher, FabricFetcherMixin):
    CANONICAL_SCHEMA_CLASS = OHLCVSchema
    SUPPORTED_INTERVALS = ("1d",)
    REQUIRES_AUTH = False
    PROVIDER_NAME = "TestProvider"
    MEDALLION_LAYER = "bronze"

    def fetch(self, ctx: NodeContext):
        del ctx
        if False:  # pragma: no cover - stub generator
            yield pa.record_batch([])


class _Counter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, str] | None]] = []

    def add(self, value: int, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))


class _FakeBus:
    def __init__(self) -> None:
        self.hash_collisions = _Counter()
        self.schema_errors = _Counter()
        self.records_persisted = _Counter()


@pytest.fixture
def sqlite_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def _valid_ohlcv_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "source_feed_id": ["source.yfinance"],
            "timestamp": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1200.0],
        }
    )


def test_loader_schema_metadata_auto_generated() -> None:
    meta = _TestFetcher.LOADER_SCHEMA_METADATA
    expected_keys = {
        "class",
        "provider",
        "source_category",
        "canonical_schema",
        "supported_intervals",
        "requires_auth",
        "medallion_layer",
    }
    assert expected_keys.issubset(meta.keys())
    assert meta["provider"] == "TestProvider"
    assert meta["canonical_schema"] == "OHLCVSchema"


def test_request_hash_deterministic() -> None:
    fetcher = _TestFetcher()
    first = fetcher._compute_request_hash(
        edge_ids=["edge-b", "edge-a"],
        time_window=(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    )
    second = fetcher._compute_request_hash(
        edge_ids=["edge-a", "edge-b"],
        time_window=(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    )
    changed_window = fetcher._compute_request_hash(
        edge_ids=["edge-a", "edge-b"],
        time_window=(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 3, tzinfo=timezone.utc),
        ),
    )

    assert first == second
    assert first != changed_window


def test_idempotency_check_returns_false_when_no_prior_row(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def _session_ctx():
        yield sqlite_session

    monkeypatch.setattr("aqp.persistence.db.get_session", _session_ctx)
    monkeypatch.setattr("aqp.data.fetchers.fabric_mixin.get_observability_bus", _FakeBus)

    fetcher = _TestFetcher()
    assert fetcher._idempotency_check("missing-hash") is False


def test_idempotency_check_returns_true_when_success_row_present(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_session.add(
        IngestionLedgerRow(
            fabric_uuid=str(uuid4()),
            data_source_id=str(uuid4()),
            request_hash="known-hash",
            execution_status="SUCCESS",
        )
    )
    sqlite_session.flush()

    @contextmanager
    def _session_ctx():
        yield sqlite_session

    fake_bus = _FakeBus()
    monkeypatch.setattr("aqp.persistence.db.get_session", _session_ctx)
    monkeypatch.setattr("aqp.data.fetchers.fabric_mixin.get_observability_bus", lambda: fake_bus)

    fetcher = _TestFetcher()
    assert fetcher._idempotency_check("known-hash") is True
    assert fake_bus.hash_collisions.calls == [
        (1, {"provider": "TestProvider"}),
    ]


def test_normalize_schema_validates_against_canonical() -> None:
    fetcher = _TestFetcher()
    invalid = _valid_ohlcv_frame().drop(columns=["volume"])

    with pytest.raises(SchemaValidationError):
        fetcher.normalize_schema(invalid)


def test_persist_to_iceberg_calls_append_arrow_with_medallion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_append_arrow(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("aqp.data.iceberg_catalog.append_arrow", _fake_append_arrow)
    monkeypatch.setattr("aqp.data.fetchers.fabric_mixin.record_lineage", lambda **_: None)
    monkeypatch.setattr("aqp.data.fetchers.fabric_mixin.get_observability_bus", _FakeBus)

    table = pa.Table.from_pandas(_valid_ohlcv_frame(), preserve_index=False).cast(
        OHLCVSchema.CANONICAL_SCHEMA
    )
    fetcher = _TestFetcher()
    rows_written = fetcher.persist_to_iceberg(
        table,
        namespace="aqp_bronze_test",
        table_name="bars",
        business_metadata=BusinessMetadata(
            data_owner="tests",
            semantic_definition="unit test",
        ),
    )

    assert rows_written == int(table.num_rows)
    assert captured["identifier"] == "aqp_bronze_test.bars"
    assert captured["medallion_layer"] == "bronze"
    assert isinstance(captured["business_metadata"], BusinessMetadata)
