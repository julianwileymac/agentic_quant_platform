"""Hermetic tests for the sink registry service."""
from __future__ import annotations

import pytest


def test_create_and_update_sink(in_memory_db) -> None:
    from aqp.data.sinks import (
        SinkValidationError,
        create_sink,
        get_sink,
        list_sink_versions,
        list_sinks,
        materialise_node_spec,
        update_sink,
    )
    from aqp.persistence import SinkRow  # noqa: F401  - registers metadata
    from aqp.persistence.db import get_session

    with get_session() as session:
        with pytest.raises(SinkValidationError):
            create_sink(session, name="bad", kind="not_a_kind")

        row = create_sink(
            session,
            name="iceberg-bars",
            kind="iceberg",
            display_name="Iceberg bars",
            config={"namespace": "aqp", "table": "bars"},
            tags=["lakehouse"],
        )
        session.commit()

    with get_session() as session:
        rows = list_sinks(session)
        assert len(rows) == 1
        assert rows[0].current_version == 1

        update_sink(
            session,
            row.id,
            display_name="Iceberg bars (renamed)",
            tags=["lakehouse", "renamed"],
        )
        session.commit()

    with get_session() as session:
        fresh = get_sink(session, row.id)
        versions = list_sink_versions(session, row.id)
        assert fresh.current_version == 2
        assert {v.version for v in versions} == {1, 2}


def test_materialise_node_spec(in_memory_db) -> None:
    from aqp.data.sinks import create_sink, materialise_node_spec
    from aqp.persistence import SinkRow  # noqa: F401
    from aqp.persistence.db import get_session

    with get_session() as session:
        row = create_sink(
            session,
            name="parquet-out",
            kind="parquet",
            display_name="Parquet out",
            config={"output_dir": "/tmp/aqp-test"},
        )
        session.commit()

    with get_session() as session:
        spec = materialise_node_spec(session, row.id, overrides={"prefix": "ovr"})
        assert spec.name == "sink.parquet"
        assert spec.kwargs["output_dir"] == "/tmp/aqp-test"
        assert spec.kwargs["prefix"] == "ovr"
