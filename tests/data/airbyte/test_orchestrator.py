from __future__ import annotations

from typing import Any

from aqp.data.airbyte.orchestrator import AirbyteOrchestrator
from aqp.data.fabric.schema_registry import OHLCVSchema


class _DummyFetcher:
    PROVIDER_NAME = "Dummy"
    CANONICAL_SCHEMA_CLASS = OHLCVSchema


def test_build_stream_config_maps_arrow_schema() -> None:
    orchestrator = AirbyteOrchestrator(client=_FakeAirbyteClient())

    stream = orchestrator.build_stream_config(_DummyFetcher())
    properties = stream["json_schema"]["properties"]

    assert stream["sync_mode"] == "incremental"
    assert stream["cursor_field"] == "timestamp"
    assert set(properties) == {
        "symbol",
        "source_feed_id",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }


def test_trigger_sync_delegates_to_client() -> None:
    client = _FakeAirbyteClient(trigger_payload={"jobId": "job-123"})
    orchestrator = AirbyteOrchestrator(client=client)

    job_id = orchestrator.trigger_sync("connection-abc")

    assert job_id == "job-123"
    assert client.trigger_calls == ["connection-abc"]


class _FakeAirbyteClient:
    def __init__(self, *, trigger_payload: dict[str, Any] | None = None) -> None:
        self.trigger_calls: list[str] = []
        self.trigger_payload = trigger_payload or {"jobId": "job-1"}

    def trigger_sync(self, connection_id: str) -> dict[str, Any]:
        self.trigger_calls.append(connection_id)
        return dict(self.trigger_payload)

    def get_job(self, _job_id: str) -> dict[str, Any]:
        return {"status": "succeeded"}
