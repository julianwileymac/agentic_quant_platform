"""Hermetic tests for `aqp_platform_core.runtime.WorkloadRuntime`.

The runtime is provider-agnostic — we register a fake
:class:`InfrastructureProvider` against the shared registry, drive
each lifecycle method, and assert the audit-sink contract + the
halt-fan-out semantics.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest

from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import (
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
)
from aqp_platform_core.models.health import HealthStatus, ProviderHealth
from aqp_platform_core.models.telemetry import MetricPoint
from aqp_platform_core.models.workloads import (
    SecretRotationResult,
    WorkloadAction,
    WorkloadExecResult,
    WorkloadLogEvent,
    WorkloadRun,
    WorkloadRunStatus,
)
from aqp_platform_core.providers import (
    InfrastructureProvider,
    InfrastructureProviderError,
    ProviderKind,
    get_provider_registry,
)
from aqp_platform_core.runtime import (
    LoggingAuditSink,
    WorkloadHaltedError,
    WorkloadRuntime,
)
from aqp_platform_core.runtime.workload import (
    WorkloadRequestContext,
    get_halt_registry,
    redact_payload,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _RecordingSink:
    """Audit sink that captures every start/finish call for assertions."""

    def __init__(self) -> None:
        self.starts: list[WorkloadRun] = []
        self.finishes: list[WorkloadRun] = []

    def start_run(self, run: WorkloadRun) -> None:
        self.starts.append(run)

    def finish_run(self, run: WorkloadRun) -> None:
        self.finishes.append(run)


class FakeProvider(InfrastructureProvider):
    provider_kind = ProviderKind.DOCKER_COMPOSE
    provider_alias = "fake_runtime_provider"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.provider_alias,
            status=HealthStatus.OK,
            available=True,
            last_probe_at=datetime.now(timezone.utc),
        )

    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        self.calls.append(("start", spec.model_dump(mode="json")))
        return DeploymentStatus(
            service_id=spec.service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.RUNNING,
            replicas_desired=spec.replicas,
            replicas_ready=spec.replicas,
        )

    async def stop(self, service_id: str, *, namespace: str | None = None) -> DeploymentStatus:
        self.calls.append(("stop", {"service_id": service_id, "namespace": namespace}))
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.STOPPED,
        )

    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        self.calls.append(("scale", {"service_id": service_id, "replicas": replicas}))
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.RUNNING,
            replicas_desired=replicas,
            replicas_ready=replicas,
        )

    async def status(self, service_id: str, *, namespace: str | None = None) -> DeploymentStatus:
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.RUNNING,
        )

    async def list_deployments(self, *, namespace: str | None = None) -> list[DeploymentStatus]:
        return [
            DeploymentStatus(
                service_id="svc-a",
                provider=self.provider_alias,
                phase=DeploymentLifecyclePhase.RUNNING,
            )
        ]

    async def restart(self, service_id: str, *, namespace: str | None = None) -> DeploymentStatus:
        self.calls.append(("restart", {"service_id": service_id}))
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.RUNNING,
        )

    async def exec(
        self,
        service_id: str,
        *,
        command: list[str],
        container: str | None = None,
        timeout_seconds: int = 60,
        stdin: bytes | None = None,
        namespace: str | None = None,
    ) -> WorkloadExecResult:
        self.calls.append(("exec", {"service_id": service_id, "command": command}))
        return WorkloadExecResult(
            service_id=service_id,
            command=command,
            stdout="hello\n",
            stderr="",
            returncode=0,
        )

    async def tail_logs(
        self,
        service_id: str,
        *,
        container: str | None = None,
        since_seconds: int | None = None,
        tail: int | None = 200,
        follow: bool = False,
        max_lines: int | None = None,
        namespace: str | None = None,
    ) -> AsyncIterator[WorkloadLogEvent]:
        for i in range(3):
            yield WorkloadLogEvent(
                service_id=service_id,
                line=f"line-{i}",
                source="stdout",
            )

    async def rotate_secret(
        self,
        service_id: str,
        *,
        secret_name: str,
        namespace: str | None = None,
    ) -> SecretRotationResult:
        return SecretRotationResult(
            service_id=service_id,
            secret_name=secret_name,
            backend="test_backend",
            rotation_id="rot-1",
            new_version="v2",
        )

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        return True


class _SlowProvider(FakeProvider):
    """Provider whose ``stop`` blocks long enough for ``halt`` to fire."""

    async def stop(self, service_id: str, *, namespace: str | None = None) -> DeploymentStatus:  # type: ignore[override]
        await asyncio.sleep(10)
        return await super().stop(service_id, namespace=namespace)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_halt_registry() -> None:
    get_halt_registry().clear_global()
    yield
    get_halt_registry().clear_global()


@pytest.fixture
def fake_provider_alias() -> str:
    """Register the FakeProvider against the shared registry for the test."""
    registry = get_provider_registry()
    # The metaclass auto-registered the FakeProvider at import time;
    # replace the cached instance to avoid leaks across tests.
    fake = FakeProvider()
    registry.replace_instance(FakeProvider.provider_alias, fake)
    yield FakeProvider.provider_alias


@pytest.fixture
def ctx() -> WorkloadRequestContext:
    return WorkloadRequestContext(
        user_id="user-1",
        org_id="org-1",
        workspace_id="ws-1",
        experiment_id="exp-1",
        test_id="test-1",
        request_id="req-1",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_redact_payload_strips_token_keys() -> None:
    raw = {
        "image": "my:latest",
        "client_secret": "abc",
        "env": {"AUTH_TOKEN": "shhh", "PORT": 8080},
        "headers": [{"Authorization": "Bearer xyz"}, {"X-Trace": "ok"}],
    }
    cleaned = redact_payload(raw)
    assert cleaned["image"] == "my:latest"
    assert cleaned["client_secret"] == "<redacted>"
    assert cleaned["env"]["AUTH_TOKEN"] == "<redacted>"
    assert cleaned["env"]["PORT"] == 8080
    assert cleaned["headers"][0]["Authorization"] == "<redacted>"
    assert cleaned["headers"][1]["X-Trace"] == "ok"


@pytest.mark.asyncio
async def test_start_writes_audit_pair(
    fake_provider_alias: str, ctx: WorkloadRequestContext
) -> None:
    sink = _RecordingSink()
    runtime = WorkloadRuntime(fake_provider_alias, audit_sink=sink)
    spec = DeploymentSpec(
        service_id="svc-a",
        image="my:latest",
        replicas=2,
        env={"PORT": "8080"},
    )
    run, status = await runtime.start(spec, ctx=ctx)
    assert isinstance(status, DeploymentStatus)
    assert status.phase == DeploymentLifecyclePhase.RUNNING
    assert len(sink.starts) == 1
    assert len(sink.finishes) == 1
    finished = sink.finishes[0]
    assert finished.status == WorkloadRunStatus.SUCCEEDED
    assert finished.action == WorkloadAction.START
    assert finished.experiment_id == "exp-1"
    assert finished.test_id == "test-1"
    assert finished.user_id == "user-1"
    assert "result_hash" in finished.result
    assert finished.duration_ms is not None


@pytest.mark.asyncio
async def test_provider_failure_marks_failed(
    fake_provider_alias: str, ctx: WorkloadRequestContext
) -> None:
    class _Boom(FakeProvider):
        async def stop(self, service_id: str, *, namespace: str | None = None) -> DeploymentStatus:  # type: ignore[override]
            raise InfrastructureProviderError(
                "blew up",
                code="oops",
                provider=self.provider_alias,
            )

    registry = get_provider_registry()
    registry.replace_instance(FakeProvider.provider_alias, _Boom())
    sink = _RecordingSink()
    runtime = WorkloadRuntime(FakeProvider.provider_alias, audit_sink=sink)
    with pytest.raises(InfrastructureProviderError):
        await runtime.stop("svc-a", ctx=ctx)
    assert sink.finishes[0].status == WorkloadRunStatus.FAILED
    assert sink.finishes[0].error == "blew up"


@pytest.mark.asyncio
async def test_halt_cancels_in_flight_action(
    fake_provider_alias: str, ctx: WorkloadRequestContext
) -> None:
    registry = get_provider_registry()
    registry.replace_instance(FakeProvider.provider_alias, _SlowProvider())
    sink = _RecordingSink()
    runtime = WorkloadRuntime(FakeProvider.provider_alias, audit_sink=sink)

    async def _go() -> None:
        await runtime.stop("svc-a", ctx=ctx)

    task = asyncio.create_task(_go())
    # Give the runtime a tick to register + dispatch.
    await asyncio.sleep(0.05)
    halted_count = runtime.halt_all(reason="test")
    assert halted_count >= 1
    with pytest.raises(WorkloadHaltedError):
        await task
    assert sink.finishes[-1].status == WorkloadRunStatus.HALTED
    assert sink.finishes[-1].halt_reason == "halt requested"


@pytest.mark.asyncio
async def test_tail_logs_writes_single_audit_row(
    fake_provider_alias: str, ctx: WorkloadRequestContext
) -> None:
    sink = _RecordingSink()
    runtime = WorkloadRuntime(fake_provider_alias, audit_sink=sink)
    events: list[WorkloadLogEvent] = []
    async for event in runtime.tail_logs("svc-a", ctx=ctx, tail=10):
        events.append(event)
    assert len(events) == 3
    # One start + one finish (no per-event audit row).
    assert len(sink.starts) == 1
    assert len(sink.finishes) == 1
    assert sink.finishes[0].action == WorkloadAction.LOGS
    assert sink.finishes[0].status == WorkloadRunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_logging_sink_emits_structured_json(
    fake_provider_alias: str, ctx: WorkloadRequestContext, caplog
) -> None:
    runtime = WorkloadRuntime(fake_provider_alias, audit_sink=LoggingAuditSink())
    caplog.set_level("INFO")
    spec = DeploymentSpec(service_id="svc-a", image="x:1", replicas=1)
    await runtime.start(spec, ctx=ctx)
    # Both phases must be emitted in JSON form so log shippers can parse.
    phases = [
        json.loads(rec.message.split("phase=start ", 1)[-1])
        if "phase=start" in rec.message
        else None
        for rec in caplog.records
        if "workload_run" in rec.message
    ]
    assert any(p is not None for p in phases)
