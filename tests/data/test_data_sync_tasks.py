from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
import uuid

import pyarrow as pa
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from aqp.data.catalog.active_metadata import BusinessMetadata
from aqp.data.fabric.idempotency import (
    check_or_insert_pending,
    compute_request_hash,
    update_ledger_status,
)
from aqp.data.fabric.schema_registry import OHLCVSchema
from aqp.data.fetchers.fabric_mixin import FabricFetcherMixin
from aqp.persistence import Base, DataSource
from aqp.persistence.models_ingestion_ledger import IngestionLedgerRow
from aqp.persistence.models_instrument_catalog import CatalogFeedEdge, InstrumentCatalog
from aqp.tasks import data_sync_tasks as data_sync_tasks_mod
from aqp.tasks.data_sync_tasks import sync_feed

pytest.importorskip("celery")


@pytest.fixture
def sqlite_session_factory(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _conn_record):  # noqa: ANN001
        # FK enforcement is intentionally OFF for this fixture. The
        # cross-table FKs (owner_user_id / workspace_id / project_id) reference
        # tenancy rows that this single-purpose sync_feed test does not seed.
        # We test request_hash + ledger transitions + persist_to_iceberg
        # delegation, not FK integrity.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    @contextmanager
    def _patched_get_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("aqp.persistence.db.get_session", _patched_get_session)
    monkeypatch.setattr("aqp.data.fabric.idempotency.get_session", _patched_get_session)
    monkeypatch.setattr("aqp.tasks.data_sync_tasks.get_session", _patched_get_session)
    monkeypatch.setattr("aqp.data.catalog.lineage.get_session", _patched_get_session)
    return SessionLocal


def _make_source(session: Session, *, name: str) -> DataSource:
    source = DataSource(
        name=name,
        display_name=f"{name} source",
        kind="rest_api",
        enabled=True,
    )
    session.add(source)
    session.flush()
    return source


def test_compute_request_hash_deterministic() -> None:
    window = (
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    first = compute_request_hash(
        data_source_id="source-1",
        edge_ids=["b", "a"],
        time_window=window,
        extras={"namespace": "aqp_bronze_test", "table_name": "prices"},
    )
    second = compute_request_hash(
        data_source_id="source-1",
        edge_ids=["a", "b"],
        time_window=window,
        extras={"table_name": "prices", "namespace": "aqp_bronze_test"},
    )
    assert first == second


def test_check_or_insert_pending_first_time_inserts_pending(sqlite_session_factory) -> None:
    ledger_id: str | None = None
    session = sqlite_session_factory()
    try:
        source = _make_source(session, name="first-time-source")
        session.commit()
        ledger_id, is_skip = check_or_insert_pending(
            data_source_id=source.id,
            request_hash="hash-1",
            requested_time_window=None,
            session=session,
        )
        assert ledger_id is not None
        assert is_skip is False
    finally:
        session.close()

    verify = sqlite_session_factory()
    try:
        row = verify.query(IngestionLedgerRow).filter(IngestionLedgerRow.id == ledger_id).first()
        assert row is not None
        assert row.execution_status == "PENDING"
    finally:
        verify.close()


def test_check_or_insert_pending_second_call_returns_skip(sqlite_session_factory) -> None:
    session = sqlite_session_factory()
    try:
        source = _make_source(session, name="skip-source")
        success_row = IngestionLedgerRow(
            fabric_uuid=str(uuid.uuid4()),
            data_source_id=source.id,
            request_hash="hash-existing",
            execution_status="SUCCESS",
        )
        session.add(success_row)
        session.commit()

        existing_id, is_skip = check_or_insert_pending(
            data_source_id=source.id,
            request_hash="hash-existing",
            requested_time_window=None,
            session=session,
        )
        assert existing_id == str(success_row.id)
        assert is_skip is True
    finally:
        session.close()


def test_update_ledger_status_terminal_sets_execution_end(sqlite_session_factory) -> None:
    session = sqlite_session_factory()
    try:
        source = _make_source(session, name="terminal-source")
        row = IngestionLedgerRow(
            fabric_uuid=str(uuid.uuid4()),
            data_source_id=source.id,
            request_hash="hash-terminal",
            execution_status="PENDING",
        )
        session.add(row)
        session.commit()

        update_ledger_status(
            str(row.id),
            status="SUCCESS",
            records_extracted=10,
            records_persisted=9,
            session=session,
        )
        session.refresh(row)
        assert row.execution_status == "SUCCESS"
        assert row.execution_end is not None
    finally:
        session.close()


def test_sync_feed_idempotent_skip(
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id: str | None = None
    session = sqlite_session_factory()
    try:
        source = _make_source(session, name="skip_feed_source")
        source_id = str(source.id)
        request_hash = compute_request_hash(
            data_source_id=source_id,
            edge_ids=[],
            time_window=None,
            extras={
                "namespace": "aqp_bronze_feeds",
                "table_name": data_sync_tasks_mod._sanitize_table_name(source.name),
                "medallion_layer": "bronze",
            },
        )
        session.add(
            IngestionLedgerRow(
                fabric_uuid=str(uuid.uuid4()),
                data_source_id=source_id,
                request_hash=request_hash,
                execution_status="SUCCESS",
            )
        )
        session.commit()
    finally:
        session.close()

    def _boom(_data_source: DataSource) -> type:
        raise RuntimeError("_resolve_loader_class should not be called")

    monkeypatch.setattr(data_sync_tasks_mod, "_resolve_loader_class", _boom)
    result = sync_feed.run(feed_id=source_id)
    assert result["skipped"] is True


def test_sync_feed_happy_path_calls_persist_to_iceberg(
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id: str | None = None
    session = sqlite_session_factory()
    try:
        source = _make_source(session, name="happy_feed_source")
        source_id = str(source.id)
        instrument = InstrumentCatalog(
            universal_ticker="AAPL",
            asset_class="equity",
            exchange_code="NASDAQ",
            metadata_blob={"name": "Apple Inc"},
        )
        session.add(instrument)
        session.flush()
        edge = CatalogFeedEdge(
            instrument_catalog_id=instrument.id,
            data_source_id=source_id,
            provider_specific_ticker="AAPL",
            edge_metadata_params={"interval": "1d"},
            is_enabled=True,
        )
        session.add(edge)
        session.commit()
    finally:
        session.close()

    class _FakeLoader(FabricFetcherMixin):
        CANONICAL_SCHEMA_CLASS = OHLCVSchema
        SUPPORTED_INTERVALS = ("1d",)
        REQUIRES_AUTH = False
        PROVIDER_NAME = "FakeLoader"

        def __init__(self, *, symbols: list[str], **_kwargs: Any) -> None:
            self.symbols = symbols

        def fetch(self, _ctx: Any):
            batch = pa.record_batch(
                {
                    "symbol": ["AAPL"],
                    "source_feed_id": ["source.fake"],
                    "timestamp": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
                    "open": [100.0],
                    "high": [101.0],
                    "low": [99.0],
                    "close": [100.5],
                    "volume": [12345.0],
                }
            )
            yield batch

    captured: dict[str, Any] = {}

    def _stub_append_arrow(
        *,
        table: pa.Table,
        identifier: str,
        medallion_layer: str,
        business_metadata: BusinessMetadata,
    ) -> int:
        captured["identifier"] = identifier
        captured["medallion_layer"] = medallion_layer
        captured["business_metadata"] = business_metadata
        return int(table.num_rows)

    monkeypatch.setattr(data_sync_tasks_mod, "_resolve_loader_class", lambda _src: _FakeLoader)
    monkeypatch.setattr("aqp.data.iceberg_catalog.append_arrow", _stub_append_arrow)

    result = sync_feed.run(
        feed_id=source_id,
        namespace="aqp_bronze_test",
        table_name="t",
        medallion_layer="bronze",
    )

    assert result["skipped"] is False
    assert result["records_persisted"] > 0
    assert captured["identifier"] == "aqp_bronze_test.t"
    assert captured["medallion_layer"] == "bronze"
    assert isinstance(captured["business_metadata"], BusinessMetadata)

    verify = sqlite_session_factory()
    try:
        ledger = (
            verify.query(IngestionLedgerRow)
            .filter(IngestionLedgerRow.id == result["ledger_id"])
            .first()
        )
        assert ledger is not None
        assert ledger.execution_status == "SUCCESS"
    finally:
        verify.close()
