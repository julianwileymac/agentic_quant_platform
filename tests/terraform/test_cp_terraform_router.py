"""CP-side TerraformRuntime + router smoke tests (Phase A of AWS hybrid).

Exercises the additions from Phase A without spinning up a full
TestClient: directly drives ``TerraformRuntime`` with a fake executor
+ asserts the audit sink + halt sentinel + spec hash behave as
documented. The CP FastAPI router itself is integration-tested
upstream in ``aqp_control_plane/tests/test_terraform_router.py``;
this file lives in the monolith tree so the cross-cut behaviour
stays visible from a single ``pytest tests/terraform/`` run.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

pytest.importorskip(
    "aqp_platform_core.models.terraform",
    reason="aqp_platform_core must be installed for CP-side tests",
)
pytest.importorskip(
    "aqp_cp.terraform.runtime",
    reason="aqp_control_plane must be installed for CP-side tests",
)

from aqp_platform_core.models.terraform import (  # noqa: E402
    TerraformRunKind,
    TerraformRunStatus,
    TerraformStackSpec,
    TerraformStateBackend,
)
from aqp_cp.terraform.audit_sink import NullTerraformAuditSink  # noqa: E402
from aqp_cp.terraform.runtime import (  # noqa: E402
    TerraformExecutor,
    TerraformRequestContext,
    TerraformRuntime,
)


class _RecordingAuditSink:
    """Captures start/finish calls so tests can assert ordering."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def start(self, *, run_id, spec, kind, **ctx):  # noqa: D401
        self.events.append(("start", run_id))

    def finish(self, *, result, **ctx):  # noqa: D401
        self.events.append(("finish", result.run_id))

    def close(self) -> None:
        return


class _StubExecutor(TerraformExecutor):
    """Executor that returns canned (rc, stdout, stderr) without spawning."""

    def __init__(self, *, rc: int = 0, stdout: str = "", stderr: str = "") -> None:
        super().__init__(workspaces_dir=str(Path.cwd() / ".tmp-cp-tf-tests"))
        self._stub_rc = rc
        self._stub_stdout = stdout
        self._stub_stderr = stderr

    def render_workspace(self, spec):  # type: ignore[override]
        target = self.workspace_path(spec)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def run_command(self, *, spec, args, env=None):  # type: ignore[override]
        return self._stub_rc, self._stub_stdout, self._stub_stderr


def _build_spec() -> TerraformStackSpec:
    return TerraformStackSpec(
        stack_name="aqp-test-stack",
        workspace_id="aqp-test-stack-dev",
        state_backend=TerraformStateBackend.LOCAL,
        hcl_modules={"main.tf": 'terraform {}\n'},
    )


def test_audit_sink_emits_start_then_finish_on_success():
    sink = _RecordingAuditSink()
    runtime = TerraformRuntime(
        executor=_StubExecutor(rc=0, stdout="Plan: 0 to add, 0 to change, 0 to destroy.\n"),
        audit_sink=sink,
    )
    ctx = TerraformRequestContext(user_id="ada")
    result = asyncio.run(
        runtime.execute(spec=_build_spec(), kind=TerraformRunKind.PLAN, ctx=ctx)
    )
    assert result.status == TerraformRunStatus.SUCCEEDED
    assert [phase for phase, _ in sink.events] == ["start", "finish"]


def test_kill_switch_rejects_apply(tmp_path):
    sentinel = tmp_path / "killed"
    sentinel.write_text("test-halt")
    sink = _RecordingAuditSink()
    runtime = TerraformRuntime(
        executor=_StubExecutor(rc=0),
        audit_sink=sink,
        kill_switch_path=str(sentinel),
    )
    ctx = TerraformRequestContext(user_id="ada")
    result = asyncio.run(
        runtime.execute(spec=_build_spec(), kind=TerraformRunKind.APPLY, ctx=ctx)
    )
    assert result.status == TerraformRunStatus.REJECTED
    assert result.halt_reason == "kill-switch"
    # The audit sink MUST still see start + finish (the rejection is a
    # legitimate finish event so the audit ledger captures it).
    assert [phase for phase, _ in sink.events] == ["start", "finish"]


def test_null_audit_sink_is_safe():
    """The default sink swallows everything — confirms zero raises."""
    runtime = TerraformRuntime(executor=_StubExecutor(rc=0))
    assert isinstance(runtime.audit_sink, NullTerraformAuditSink)
    ctx = TerraformRequestContext(user_id="ada")
    asyncio.run(
        runtime.execute(spec=_build_spec(), kind=TerraformRunKind.PLAN, ctx=ctx)
    )


def test_spec_hash_is_stable():
    s1 = _build_spec()
    s2 = _build_spec()
    assert s1.compute_hash() == s2.compute_hash()
