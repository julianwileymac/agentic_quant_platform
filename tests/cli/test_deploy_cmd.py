"""``aqp deploy`` CLI smoke tests.

The tests stub :class:`TerraformRuntime` so the suite never shells
out to terraform / k3d / docker.
"""
from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    # Newer Typer versions removed the mix_stderr kwarg; the default
    # already merges stderr into the captured output.
    return CliRunner()


def _patch_runtime(monkeypatch, *, plan_exit: int = 0, apply_exit: int = 0, destroy_exit: int = 0):
    """Stub TerraformRuntime so plan/apply/destroy never shell out."""

    class _StubResult:
        def __init__(self, exit_code: int, status: str = "completed") -> None:
            self.exit_code = exit_code
            self.status = status
            self.duration_ms = 1.0
            self.error = None
            self.plan_summary = {}
            self.stdout_log_uri = None

    class _StubRuntime:
        def __init__(self, *, spec, workspace_id, prerendered_workspace_dir=None, **_kw):
            self.spec = spec
            self.workspace_id = workspace_id
            self.prerendered_workspace_dir = prerendered_workspace_dir

        def plan(self, *, destroy: bool = False, **_kw) -> Any:
            return _StubResult(plan_exit)

        def apply(self, **_kw) -> Any:
            return _StubResult(apply_exit)

        def destroy(self, **_kw) -> Any:
            return _StubResult(destroy_exit)

        def refresh(self, **_kw) -> Any:
            return _StubResult(0)

    monkeypatch.setattr("aqp.terraform.runtime.TerraformRuntime", _StubRuntime)
    monkeypatch.setattr("aqp.cli.deploy_cmd._ensure_terraform_binary", lambda: "terraform")
    monkeypatch.setattr("aqp.cli.deploy_cmd._ensure_k3d_binary", lambda: "k3d")
    monkeypatch.setattr(
        "aqp.cli.deploy_cmd._read_terraform_outputs",
        lambda: {
            "frontend_url": "http://localhost:8000/",
            "api_url": "http://localhost:8000/api",
            "endpoints": {
                "registry": "localhost:5001",
                "namespace": "aqp-local",
            },
        },
    )


def test_deploy_plan_invokes_runtime(runner, monkeypatch):
    _patch_runtime(monkeypatch)
    from aqp.cli.deploy_cmd import app

    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "plan" in result.stdout.lower()


def test_deploy_up_runs_plan_then_apply(runner, monkeypatch):
    _patch_runtime(monkeypatch, plan_exit=2, apply_exit=0)
    from aqp.cli.deploy_cmd import app

    result = runner.invoke(app, ["up"])
    assert result.exit_code == 0, result.output
    out = result.output.lower()
    # Plan + apply status lines AND the endpoints rollup all appear when
    # the up pipeline completes successfully.
    assert "apply" in out
    assert "frontend_url" in result.output


def test_deploy_apply_aborts_when_plan_fails(runner, monkeypatch):
    _patch_runtime(monkeypatch, plan_exit=1)
    from aqp.cli.deploy_cmd import app

    result = runner.invoke(app, ["apply"])
    assert result.exit_code != 0


def test_deploy_down_requires_confirmation(runner, monkeypatch):
    _patch_runtime(monkeypatch)
    from aqp.cli.deploy_cmd import app

    # Without -y the CLI prompts; respond "no" -> exit 0 without running destroy.
    result = runner.invoke(app, ["down"], input="n\n")
    assert result.exit_code == 0
    assert "aborted" in result.stdout.lower()


def test_deploy_down_with_yes_flag_runs_destroy(runner, monkeypatch):
    _patch_runtime(monkeypatch)
    from aqp.cli.deploy_cmd import app

    result = runner.invoke(app, ["down", "--yes"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "destroy" in result.stdout.lower()


def test_deploy_endpoints_prints_outputs(runner, monkeypatch):
    _patch_runtime(monkeypatch)
    from aqp.cli.deploy_cmd import app

    result = runner.invoke(app, ["endpoints"])
    assert result.exit_code == 0
    assert "frontend_url" in result.stdout
    assert "api_url" in result.stdout


def test_deploy_app_registered_on_main():
    from aqp.cli.main import app

    # The command tree should expose 'deploy' as a subcommand.
    cmds = {c.name for c in getattr(app, "registered_groups", [])}
    assert "deploy" in cmds
