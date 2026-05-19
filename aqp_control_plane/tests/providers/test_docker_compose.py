"""docker_compose provider — focused unit tests over the parsing helpers."""
from __future__ import annotations

import json

import pytest

from aqp_cp.providers.docker_compose import (
    DockerComposeProvider,
    _iter_json_lines,
    _looks_like_secret,
    _parse_docker_stats,
    _parse_ps_output,
)
from aqp_platform_core.models.deployment import DeploymentLifecyclePhase


class TestIterJsonLines:
    def test_jsonl_format(self) -> None:
        payload = '{"a": 1}\n{"a": 2}\n'
        entries = list(_iter_json_lines(payload))
        assert entries == [{"a": 1}, {"a": 2}]

    def test_array_format(self) -> None:
        payload = '[{"a": 1}, {"a": 2}]'
        entries = list(_iter_json_lines(payload))
        assert entries == [{"a": 1}, {"a": 2}]

    def test_empty(self) -> None:
        assert list(_iter_json_lines("")) == []
        assert list(_iter_json_lines("   \n   ")) == []

    def test_skips_garbage_lines(self) -> None:
        payload = '{"a": 1}\nnot-json\n{"b": 2}\n'
        entries = list(_iter_json_lines(payload))
        assert entries == [{"a": 1}, {"b": 2}]


class TestParsePsOutput:
    def test_no_containers_returns_stopped(self) -> None:
        status = _parse_ps_output("", service_id="svc", provider_alias="dc")
        assert status.service_id == "svc"
        assert status.provider == "dc"
        assert status.phase == DeploymentLifecyclePhase.STOPPED
        assert status.replicas_ready == 0

    def test_all_running_returns_running(self) -> None:
        payload = "\n".join(
            json.dumps({"State": "running", "Image": "x:1"}) for _ in range(3)
        )
        status = _parse_ps_output(payload, service_id="svc", provider_alias="dc")
        assert status.phase == DeploymentLifecyclePhase.RUNNING
        assert status.replicas_desired == 3
        assert status.replicas_ready == 3
        assert status.image == "x:1"

    def test_partial_running_returns_degraded(self) -> None:
        payload = "\n".join(
            [
                json.dumps({"State": "running", "Image": "x:1"}),
                json.dumps({"State": "exited", "Image": "x:1"}),
            ]
        )
        status = _parse_ps_output(payload, service_id="svc", provider_alias="dc")
        assert status.phase == DeploymentLifecyclePhase.DEGRADED
        assert status.replicas_ready == 1
        assert status.replicas_desired == 2


class TestLooksLikeSecret:
    @pytest.mark.parametrize(
        "key,is_secret",
        [
            ("AQP_DATABASE_PASSWORD", True),
            ("AUTH0_CLIENT_SECRET", True),
            ("API_TOKEN", True),
            ("MY_PRIVATE_KEY", True),
            ("AWS_CREDENTIAL_CHAIN", True),
            ("AQP_LOG_LEVEL", False),
            ("PYTHONPATH", False),
            ("REDIS_URL", False),
        ],
    )
    def test_redaction_filter(self, key: str, is_secret: bool) -> None:
        assert _looks_like_secret(key) is is_secret


class TestParseDockerStats:
    def test_handles_missing_fields(self) -> None:
        cpu, mem_pct, mem_used = _parse_docker_stats({})
        assert cpu == 0.0
        assert mem_pct == 0.0
        assert mem_used == 0.0

    def test_calculates_cpu_percentage(self) -> None:
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200},
                "system_cpu_usage": 1000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 500,
            },
            "memory_stats": {"usage": 50, "limit": 100},
        }
        cpu, mem_pct, mem_used = _parse_docker_stats(stats)
        # cpu_delta=100, system_delta=500, online=2 -> 100/500 * 2 * 100 = 40.0
        assert cpu == pytest.approx(40.0)
        assert mem_pct == pytest.approx(50.0)
        assert mem_used == pytest.approx(50.0)


class TestProviderConstructor:
    def test_env_var_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AQP_CP_COMPOSE_FILE", "/tmp/custom.yml")
        monkeypatch.setenv("AQP_CP_COMPOSE_PROJECT_NAME", "custom-proj")
        provider = DockerComposeProvider()
        assert provider.compose_file == "/tmp/custom.yml"
        assert provider.project_name == "custom-proj"
