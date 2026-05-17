"""Lineage observer tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from aqp.data.catalog.lineage import (
    BaseLineageObserver,
    LineageBus,
    LineageEvent,
    LineageWriter,
    record_lineage,
)
from aqp.persistence.models_lineage import (
    LINEAGE_TRANSFORM_KINDS,
    DataLineageEvent,
)


def test_lineage_event_normalisation() -> None:
    event = LineageEvent(
        transform_kind="iceberg_append",
        target_table_id="aqp_silver_alpha_vantage.daily_bars",
    )
    assert event.normalised_kind() == "iceberg_append"
    blank = LineageEvent(transform_kind=" ")
    assert blank.normalised_kind() == "unknown"


def test_lineage_kind_constants_are_strings() -> None:
    assert "iceberg_append" in LINEAGE_TRANSFORM_KINDS
    assert "schema_drift" in LINEAGE_TRANSFORM_KINDS
    assert "mcp_tool" in LINEAGE_TRANSFORM_KINDS


def test_lineage_writer_persists_event(in_memory_db) -> None:
    Session = in_memory_db
    writer = LineageWriter()
    row_id = writer.record(
        LineageEvent(
            transform_kind="iceberg_append",
            target_table_id="aqp_silver_alpha_vantage.daily_bars",
            actor="iceberg_catalog",
            actor_kind="service",
            rows_written=1234,
            medallion_layer="silver",
            summary="appended 1234 rows",
        )
    )
    assert row_id is not None

    with Session() as session:
        rows = session.execute(select(DataLineageEvent)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.transform_kind == "iceberg_append"
        assert row.medallion_layer == "silver"
        assert row.rows_written == "1234"
        assert row.summary == "appended 1234 rows"


def test_record_lineage_helper_and_suppress(in_memory_db) -> None:
    Session = in_memory_db
    record_lineage(
        "iceberg_append",
        target="aqp_silver_alpha_vantage.daily_bars",
        rows_written=1,
    )
    with LineageWriter.suppress():
        record_lineage("iceberg_append", target="suppressed.table")
    record_lineage("dbt", target="aqp_gold_features.daily_features")

    with Session() as session:
        rows = session.execute(select(DataLineageEvent)).scalars().all()
        kinds = sorted(row.transform_kind for row in rows)
        targets = sorted(row.target_table_id for row in rows)
    assert kinds == ["dbt", "iceberg_append"]
    assert targets == [
        "aqp_gold_features.daily_features",
        "aqp_silver_alpha_vantage.daily_bars",
    ]


def test_lineage_bus_observers_fire(in_memory_db) -> None:
    seen: list[LineageEvent] = []

    class CapturingObserver(BaseLineageObserver):
        name = "capturing"

        def handle(self, event: LineageEvent) -> None:
            seen.append(event)

    bus = LineageBus()
    obs = CapturingObserver()
    bus.register(obs)
    bus.emit(LineageEvent(transform_kind="materialize", target_table_id="t1"))
    bus.unregister(obs)
    bus.emit(LineageEvent(transform_kind="materialize", target_table_id="t2"))
    assert len(seen) == 1
    assert seen[0].target_table_id == "t1"
