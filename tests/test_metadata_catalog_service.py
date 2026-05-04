from __future__ import annotations

from datetime import datetime


def test_metadata_catalog_lists_registered_and_iceberg_only_datasets(in_memory_db, monkeypatch):
    from aqp.persistence.models import DatasetCatalog, DatasetVersion
    from aqp.services import metadata_catalog_service as service_mod
    from aqp.services.metadata_catalog_service import MetadataCatalogService

    Session = in_memory_db
    with Session() as session:
        catalog = DatasetCatalog(
            name="bars.default",
            provider="alpha_vantage",
            domain="market.bars",
            frequency="1d",
            storage_uri="/tmp/bars",
            tags=["alpha_vantage", "1d"],
            updated_at=datetime(2026, 5, 4),
        )
        session.add(catalog)
        session.flush()
        session.add(
            DatasetVersion(
                catalog_id=catalog.id,
                version=1,
                status="active",
                row_count=100,
                symbol_count=2,
                file_count=2,
                dataset_hash="abc",
                created_at=datetime(2026, 5, 4),
            )
        )
        session.commit()

    def _fake_tables(namespace=None):
        return ["aqp.intraday"] if namespace in (None, "aqp") else []

    monkeypatch.setattr(service_mod.iceberg_catalog, "list_tables", _fake_tables)

    rows = MetadataCatalogService().list_datasets(limit=10)

    names = {row["name"] for row in rows}
    assert "bars.default" in names
    assert "intraday" in names
    registered = next(row for row in rows if row["name"] == "bars.default")
    assert registered["provider"] == "alpha_vantage"
    assert registered["latest_row_count"] == 100


def test_metadata_catalog_registered_namespace_filters_non_iceberg(in_memory_db, monkeypatch):
    from aqp.persistence.models import DatasetCatalog
    from aqp.services import metadata_catalog_service as service_mod
    from aqp.services.metadata_catalog_service import MetadataCatalogService

    Session = in_memory_db
    with Session() as session:
        session.add(
            DatasetCatalog(
                name="bars.default",
                provider="alpha_vantage",
                domain="market.bars",
                storage_uri="/tmp/bars",
            )
        )
        session.add(
            DatasetCatalog(
                name="iceberg.table",
                provider="iceberg",
                domain="market.bars",
                iceberg_identifier="aqp.table",
            )
        )
        session.commit()

    monkeypatch.setattr(service_mod.iceberg_catalog, "list_tables", lambda namespace=None: [])

    rows = MetadataCatalogService().list_datasets(namespace="__registered__", limit=10)

    assert [row["name"] for row in rows] == ["bars.default"]


def test_metadata_catalog_namespace_filter_applies_before_limit(in_memory_db, monkeypatch):
    """SQL limit must apply after namespace filter (not the global updated_at top-N)."""
    from aqp.persistence.models import DatasetCatalog
    from aqp.services import metadata_catalog_service as service_mod
    from aqp.services.metadata_catalog_service import MetadataCatalogService

    Session = in_memory_db
    with Session() as session:
        for idx in range(5):
            session.add(
                DatasetCatalog(
                    name=f"other.{idx}",
                    provider="other",
                    domain="market.bars",
                    storage_uri="/tmp/x",
                    iceberg_identifier=None,
                    updated_at=datetime(2026, 5, 4, 12, 0, idx),
                )
            )
        session.add(
            DatasetCatalog(
                name="bars.default",
                provider="alpha_vantage",
                domain="market.bars",
                storage_uri="/tmp/bars",
                iceberg_identifier=None,
                updated_at=datetime(2026, 5, 3, 0, 0, 0),
            )
        )
        session.commit()

    monkeypatch.setattr(service_mod.iceberg_catalog, "list_tables", lambda namespace=None: [])

    rows = MetadataCatalogService().list_datasets(namespace="alpha_vantage", limit=10)
    assert [row["name"] for row in rows] == ["bars.default"]


def test_metadata_catalog_iceberg_namespace_matches_identifier_prefix(in_memory_db, monkeypatch):
    from aqp.persistence.models import DatasetCatalog
    from aqp.services import metadata_catalog_service as service_mod
    from aqp.services.metadata_catalog_service import MetadataCatalogService

    Session = in_memory_db
    with Session() as session:
        session.add(
            DatasetCatalog(
                name="alpha_vantage.time_series_intraday",
                provider="alpha_vantage",
                domain="market.bars.intraday",
                iceberg_identifier="aqp_alpha_vantage.time_series_intraday",
            )
        )
        session.add(
            DatasetCatalog(
                name="bars.default",
                provider="alpha_vantage",
                domain="market.bars",
                iceberg_identifier=None,
            )
        )
        session.commit()

    monkeypatch.setattr(service_mod.iceberg_catalog, "list_tables", lambda namespace=None: [])

    rows = MetadataCatalogService().list_datasets(namespace="aqp_alpha_vantage", limit=10)
    assert [row["name"] for row in rows] == ["alpha_vantage.time_series_intraday"]


def test_metadata_catalog_universe_namespace_returns_instruments(in_memory_db) -> None:
    from datetime import UTC, datetime

    from aqp.persistence.models import Instrument
    from aqp.services.metadata_catalog_service import MetadataCatalogService

    Session = in_memory_db
    now = datetime.now(UTC)
    with Session() as session:
        session.add(
            Instrument(
                vt_symbol="TST.NASDAQ",
                ticker="TST",
                exchange="NASDAQ",
                asset_class="equity",
                security_type="equity",
                updated_at=now,
            )
        )
        session.commit()

    rows = MetadataCatalogService().list_datasets(namespace="__universe__", limit=10)
    assert len(rows) == 1
    assert rows[0]["entry_kind"] == "instrument"
    assert rows[0]["vt_symbol"] == "TST.NASDAQ"
    assert rows[0]["ticker"] == "TST"
