from __future__ import annotations

from aqp.data.airbyte import AirbyteConnectionSpec, ConnectorKind, EmbeddedAirbyteRunner
from aqp.data.airbyte.registry import (
    connector_summary,
    get_connector,
    list_connectors,
    stream_entity_mappings,
)
from aqp.data.engine.airbyte import build_airbyte_staging_manifest


def test_airbyte_registry_exposes_financial_and_service_connectors() -> None:
    connectors = list_connectors(kind=ConnectorKind.SOURCE)

    connector_ids = {connector.id for connector in connectors}
    assert {"alpha-vantage", "fred", "sec", "postgres", "s3-minio"} <= connector_ids
    assert connector_summary()["sources"] >= 5


def test_airbyte_registry_exposes_entity_mappings() -> None:
    mappings = stream_entity_mappings("alpha-vantage")

    assert {"stream": "time_series_intraday", "entity_kind": "instrument"} in [
        {"stream": item["stream"], "entity_kind": item["entity_kind"]}
        for item in mappings
    ]


def test_embedded_runner_dry_run_does_not_require_pyairbyte() -> None:
    runner = EmbeddedAirbyteRunner()

    spec = runner.spec("alpha-vantage")
    discovered = runner.discover("alpha-vantage", dry_run=True)
    checked = runner.check("alpha-vantage", {}, dry_run=True)

    assert spec["connector"]["id"] == "alpha-vantage"
    assert discovered["catalog"]["streams"]
    assert checked["ok"] is True


def test_airbyte_staging_manifest_uses_existing_engine_nodes() -> None:
    connector = get_connector("alpha-vantage")
    connection = AirbyteConnectionSpec.model_validate(
        {
            "name": "Alpha Vantage staging",
            "source": {"connector_id": connector.id},
            "destination": {
                "connector_id": "destination-s3-minio",
                "staging_uri": "s3://aqp-datasets/airbyte/alpha-vantage",
            },
            "streams": connector.streams,
            "namespace": "aqp_airbyte",
        },
    )
    manifest = build_airbyte_staging_manifest(
        connection=connection,
        stream="time_series_intraday",
    )

    assert manifest["source"]["name"] == "source.s3"
    assert manifest["sink"]["name"] == "sink.iceberg"
    assert manifest["compute"]["backend"] == "auto"
