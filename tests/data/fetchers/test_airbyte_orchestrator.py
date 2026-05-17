from __future__ import annotations

from aqp.data.airbyte.orchestrator import AirbyteOrchestrator
from aqp.data.fabric.schema_registry import OHLCVSchema
from aqp.data.fetchers.fabric_mixin import FabricFetcherMixin


class _StubFetcher(FabricFetcherMixin):
    CANONICAL_SCHEMA_CLASS = OHLCVSchema
    SUPPORTED_INTERVALS = ("1d",)
    PROVIDER_NAME = "stub"
    REQUIRES_AUTH = False


class _StubAirbyteClient:
    def trigger_sync(self, connection_id: str) -> dict[str, str]:
        return {"jobId": f"job-{connection_id}"}

    def get_job(self, job_id: str) -> dict[str, str]:
        return {"status": "succeeded", "jobId": job_id}


def test_build_stream_config_uses_canonical_schema() -> None:
    orchestrator = AirbyteOrchestrator(client=_StubAirbyteClient())
    config = orchestrator.build_stream_config(_StubFetcher())

    assert config["stream"]["name"] == "stub_OHLCVSchema"
    properties = config["stream"]["json_schema"]["properties"]
    assert "symbol" in properties
    assert config["stream"]["default_cursor_field"] == "timestamp"
    assert config["sync_mode"] == "incremental"
