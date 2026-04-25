"""Tests for the identifier graph — registry, resolver and data links."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from aqp.data.catalog import register_data_links
from aqp.data.sources.base import IdentifierSpec
from aqp.data.sources.registry import (
    get_data_source,
    list_data_sources,
    set_data_source_enabled,
    upsert_data_source,
)
from aqp.data.sources.resolvers.identifiers import IdentifierResolver
from aqp.persistence.models import (
    DataLink,
    DataSource,
    DatasetCatalog,
    DatasetVersion,
    IdentifierLink,
    Instrument,
)


def _seed_instrument(session_factory, vt_symbol: str = "AAPL.NASDAQ") -> str:
    with session_factory() as session:
        inst = Instrument(
            vt_symbol=vt_symbol,
            ticker=vt_symbol.split(".", 1)[0],
            exchange=vt_symbol.split(".", 1)[1] if "." in vt_symbol else "NASDAQ",
            asset_class="equity",
            security_type="equity",
            identifiers={"vt_symbol": vt_symbol, "ticker": vt_symbol.split(".", 1)[0]},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(inst)
        session.commit()
        return inst.id


def test_registry_upsert_and_toggle(patched_db, sqlite_session_factory):
    row = upsert_data_source(
        name="test-source",
        display_name="Test Source",
        kind="rest_api",
        auth_type="api_key",
        base_url="https://example.test",
        capabilities={"domains": ["market.bars"]},
    )
    assert row["name"] == "test-source"
    assert row["enabled"] is True

    fetched = get_data_source("test-source")
    assert fetched is not None
    assert fetched["display_name"] == "Test Source"

    toggled = set_data_source_enabled("test-source", False)
    assert toggled is not None
    assert toggled["enabled"] is False

    all_rows = list_data_sources()
    assert any(r["name"] == "test-source" for r in all_rows)
    enabled_rows = list_data_sources(enabled_only=True)
    assert all(r["enabled"] for r in enabled_rows)


def test_registry_coerces_json_string_fields(patched_db, sqlite_session_factory):
    with sqlite_session_factory() as session:
        session.add(
            DataSource(
                name="legacy-json",
                display_name="Legacy JSON Source",
                kind="rest_api",
                auth_type="none",
                protocol="https/json",
                capabilities='{"domains": ["market.bars"]}',
                rate_limits='{"req_per_minute": 5}',
                meta='{"notes": "legacy"}',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        session.commit()

    row = get_data_source("legacy-json")
    assert row is not None
    assert row["capabilities"]["domains"] == ["market.bars"]
    assert row["rate_limits"]["req_per_minute"] == 5
    assert row["meta"]["notes"] == "legacy"


def test_registry_fallback_when_table_unavailable(monkeypatch):
    @contextmanager
    def _broken_session():
        raise SQLAlchemyError("data_sources missing")
        yield

    monkeypatch.setattr("aqp.data.sources.registry.get_session", _broken_session)

    rows = list_data_sources()
    assert any(row["name"] == "alpha_vantage" for row in rows)
    assert get_data_source("alpha_vantage") is not None


def test_resolver_upsert_and_resolve(patched_db, sqlite_session_factory):
    vt_symbol = "MSFT.NASDAQ"
    instrument_id = _seed_instrument(sqlite_session_factory, vt_symbol)

    resolver = IdentifierResolver()
    links = resolver.upsert_links(
        [
            IdentifierSpec(
                scheme="cik",
                value="789019",
                entity_kind="instrument",
                instrument_vt_symbol=vt_symbol,
                meta={"sec": "msft"},
            ),
            IdentifierSpec(
                scheme="isin",
                value="US5949181045",
                entity_kind="instrument",
                instrument_vt_symbol=vt_symbol,
            ),
        ]
    )
    assert len(links) == 2

    # Reverse lookup
    inst = resolver.resolve_instrument("cik", "789019")
    assert inst is not None
    assert inst.vt_symbol == vt_symbol

    inst_by_ticker = resolver.resolve_instrument("ticker", "MSFT")
    assert inst_by_ticker is not None
    assert inst_by_ticker.id == instrument_id

    graph = resolver.instrument_identifiers(instrument_id)
    schemes = {g["scheme"] for g in graph}
    assert {"cik", "isin"}.issubset(schemes)

    # Idempotent re-upsert
    again = resolver.upsert_links(
        [
            IdentifierSpec(
                scheme="cik",
                value="789019",
                entity_kind="instrument",
                instrument_vt_symbol=vt_symbol,
            )
        ]
    )
    assert len(again) == 1  # same row returned, no duplicates

    # Write-through to the legacy JSON blob
    with sqlite_session_factory() as session:
        inst = session.get(Instrument, instrument_id)
        assert (inst.identifiers or {}).get("cik") == "789019"


def test_resolver_time_versioning(patched_db, sqlite_session_factory):
    vt_symbol = "GOOG.NASDAQ"
    instrument_id = _seed_instrument(sqlite_session_factory, vt_symbol)
    resolver = IdentifierResolver()

    older = datetime(2015, 1, 1)
    newer = datetime(2020, 1, 1)
    resolver.upsert_links(
        [
            IdentifierSpec(
                scheme="ticker",
                value="GOOG",
                entity_kind="instrument",
                instrument_vt_symbol=vt_symbol,
                valid_from=older,
                valid_to=newer,
            ),
            IdentifierSpec(
                scheme="ticker",
                value="GOOG",
                entity_kind="instrument",
                instrument_vt_symbol=vt_symbol,
                valid_from=newer,
            ),
        ]
    )
    # Two rows share (entity_kind, scheme, value) but different valid_from.
    with sqlite_session_factory() as session:
        rows = session.query(IdentifierLink).filter_by(scheme="ticker").all()
        assert len(rows) == 2


def test_data_links_emission(patched_db, sqlite_session_factory):
    vt_symbol = "TSLA.NASDAQ"
    instrument_id = _seed_instrument(sqlite_session_factory, vt_symbol)
    upsert_data_source(name="yfinance", display_name="yfinance")

    # Seed a dataset_catalog + dataset_version manually to link against.
    with sqlite_session_factory() as session:
        catalog = DatasetCatalog(
            name="bars.default",
            provider="yfinance",
            domain="market.bars",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(catalog)
        session.flush()
        version = DatasetVersion(
            catalog_id=catalog.id,
            version=1,
            status="active",
            row_count=1,
            symbol_count=1,
            file_count=1,
            created_at=datetime.utcnow(),
        )
        session.add(version)
        session.commit()
        version_id = version.id

    persisted = register_data_links(
        dataset_version_id=version_id,
        source_name="yfinance",
        entity_rows=[
            {
                "entity_kind": "instrument",
                "entity_id": vt_symbol,
                "instrument_vt_symbol": vt_symbol,
                "coverage_start": datetime(2024, 1, 1),
                "coverage_end": datetime(2024, 2, 1),
                "row_count": 22,
            }
        ],
    )
    assert len(persisted) == 1

    with sqlite_session_factory() as session:
        rows = session.query(DataLink).all()
        assert len(rows) == 1
        assert rows[0].instrument_id == instrument_id
        assert rows[0].row_count == 22
