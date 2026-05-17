from __future__ import annotations

import json
import re
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from aqp.persistence import Base, DataSource
from aqp.persistence.models_ingestion_ledger import (
    FabricVersionSnapshot,
    IngestionLedgerRow,
)
from aqp.persistence.models_instrument_catalog import (
    CatalogFeedEdge,
    InstrumentCatalog,
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _conn_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    sess = sessionmaker(bind=engine, future=True)()
    try:
        yield sess
    finally:
        sess.close()


def _make_data_source(session: Session, *, suffix: str) -> DataSource:
    row = DataSource(
        name=f"fabric-source-{suffix}",
        display_name=f"Fabric Source {suffix}",
    )
    session.add(row)
    session.flush()
    return row


def test_instrument_catalog_content_hash_listener_fires_on_insert(session: Session) -> None:
    row = InstrumentCatalog(
        universal_ticker="AAPL",
        asset_class="equity",
        exchange_code="NASDAQ",
        metadata_blob={"sector": "technology"},
    )
    session.add(row)
    session.flush()

    assert row.content_hash
    assert _HEX64_RE.fullmatch(row.content_hash) is not None


def test_instrument_catalog_content_hash_changes_on_update(session: Session) -> None:
    row = InstrumentCatalog(
        universal_ticker="MSFT",
        asset_class="equity",
        exchange_code="NASDAQ",
        metadata_blob={"sector": "technology"},
    )
    session.add(row)
    session.flush()
    first_hash = row.content_hash

    row.metadata_blob = {"sector": "technology", "industry": "software"}
    session.flush()

    assert row.content_hash != first_hash


def test_catalog_feed_edge_unique_constraint(session: Session) -> None:
    source = _make_data_source(session, suffix="unique")
    catalog = InstrumentCatalog(
        universal_ticker="QQQ",
        asset_class="etf",
        exchange_code="NASDAQ",
    )
    session.add(catalog)
    session.flush()

    first = CatalogFeedEdge(
        instrument_catalog_id=catalog.id,
        data_source_id=source.id,
        provider_specific_ticker="QQQ",
    )
    session.add(first)
    session.flush()

    duplicate = CatalogFeedEdge(
        instrument_catalog_id=catalog.id,
        data_source_id=source.id,
        provider_specific_ticker="QQQ",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.flush()


def test_ingestion_ledger_request_hash_index_exists() -> None:
    index_names = {idx.name for idx in IngestionLedgerRow.__table__.indexes}
    assert "ix_ingestion_ledger_request_hash_status" in index_names


def test_data_source_extension_columns_present() -> None:
    column_names = {column.name for column in DataSource.__table__.columns}
    assert {
        "loader_class_path",
        "rate_limit_params",
        "execution_schedule",
    }.issubset(column_names)


def test_fabric_version_snapshot_round_trip(session: Session) -> None:
    fabric_uuid = str(uuid.uuid4())
    row = FabricVersionSnapshot(
        fabric_uuid=fabric_uuid,
        object_kind="instrument_catalog",
        version_vector={"InstrumentCatalog": 1},
        snapshot_data={"universal_ticker": "AAPL"},
        content_hash="a" * 64,
    )
    session.add(row)
    session.commit()

    loaded = session.query(FabricVersionSnapshot).filter_by(id=row.id).one()

    version_vector = loaded.version_vector
    if isinstance(version_vector, str):
        version_vector = json.loads(version_vector)

    assert loaded.fabric_uuid == fabric_uuid
    assert loaded.object_kind == "instrument_catalog"
    assert version_vector == {"InstrumentCatalog": 1}
