"""Hermetic ORM tests for the data layer expansion models.

Covers SinkRow, SinkVersionRow, MarketDataProducerRow, and
StreamingDatasetLink — verifies columns, defaults, indexes, and
unique constraints round-trip through SQLite.
"""
from __future__ import annotations

from datetime import datetime

import pytest


def _create_all_layer_models(in_memory_db):
    # The fixture builds Base.metadata.create_all already, but the new models
    # only get registered when their modules are imported.
    from aqp.persistence import (  # noqa: F401
        MarketDataProducerRow,
        SinkRow,
        SinkVersionRow,
        StreamingDatasetLink,
    )
    from aqp.persistence.db import get_session

    return get_session


def test_sink_row_round_trip(in_memory_db) -> None:
    from aqp.persistence import SinkRow, SinkVersionRow

    get_session = _create_all_layer_models(in_memory_db)
    with get_session() as session:
        row = SinkRow(
            name="iceberg-bars",
            kind="iceberg",
            display_name="Iceberg bars",
            config_json={"namespace": "aqp", "table": "bars"},
            tags=["lakehouse"],
        )
        session.add(row)
        session.flush()
        version = SinkVersionRow(
            sink_id=row.id,
            version=1,
            spec_hash="hash" * 8,
            payload={"name": row.name, "kind": row.kind},
            created_by="test",
        )
        session.add(version)
    with get_session() as session:
        rows = session.query(SinkRow).all()
        versions = session.query(SinkVersionRow).all()
        assert len(rows) == 1
        assert rows[0].name == "iceberg-bars"
        assert rows[0].current_version == 1
        assert rows[0].enabled is True
        assert rows[0].requires_manifest_node is True
        assert rows[0].config_json == {"namespace": "aqp", "table": "bars"}
        assert len(versions) == 1
        assert versions[0].sink_id == rows[0].id
        assert versions[0].version == 1


def test_sink_unique_per_project(in_memory_db) -> None:
    from sqlalchemy.exc import IntegrityError

    from aqp.persistence import SinkRow

    get_session = _create_all_layer_models(in_memory_db)
    with get_session() as session:
        session.add(SinkRow(name="dupe", kind="iceberg", display_name="A"))
        session.add(SinkRow(name="dupe", kind="parquet", display_name="B"))
        with pytest.raises(IntegrityError):
            session.flush()


def test_market_data_producer_round_trip(in_memory_db) -> None:
    from aqp.persistence import MarketDataProducerRow

    get_session = _create_all_layer_models(in_memory_db)
    with get_session() as session:
        row = MarketDataProducerRow(
            name="alphavantage",
            kind="alphavantage",
            runtime="cluster_proxy",
            display_name="Alpha Vantage Producer",
            topics=["alphavantage.intraday.v1"],
            desired_replicas=0,
        )
        session.add(row)
        session.flush()
    with get_session() as session:
        row = (
            session.query(MarketDataProducerRow)
            .filter(MarketDataProducerRow.name == "alphavantage")
            .first()
        )
        assert row is not None
        assert row.kind == "alphavantage"
        assert row.runtime == "cluster_proxy"
        assert row.last_status == "unknown"
        assert row.enabled is True


def test_streaming_dataset_link_unique_natural_key(in_memory_db) -> None:
    from sqlalchemy.exc import IntegrityError

    from aqp.persistence import StreamingDatasetLink

    get_session = _create_all_layer_models(in_memory_db)
    with get_session() as session:
        session.add(
            StreamingDatasetLink(
                dataset_catalog_id=None,
                kind="kafka_topic",
                target_ref="market.bar.v1",
                direction="source",
            )
        )
        session.add(
            StreamingDatasetLink(
                dataset_catalog_id=None,
                kind="kafka_topic",
                target_ref="market.bar.v1",
                direction="source",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
