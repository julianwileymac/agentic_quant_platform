"""Smoke tests for the top-level CLI surface."""

from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from aqp_cli import __version__
from aqp_cli.cli import app

runner = CliRunner()


def test_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_all_command_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in (
        "setup",
        "services",
        "update",
        "auth",
        "account",
        "config",
        "cp",
        "deploy",
        "viz",
        "client",
        "ide",
        "tools",
    ):
        assert group in result.stdout


def test_auth_direct_requires_understanding() -> None:
    """--direct without --i-understand exits non-zero per rule 27."""
    result = runner.invoke(app, ["auth", "login", "--direct"])
    assert result.exit_code != 0


@respx.mock
def test_auth_whoami_calls_api(monkeypatch) -> None:
    monkeypatch.setenv("AQP_ACCESS_TOKEN", "tok_test_123")
    route = respx.get("http://localhost:8000/auth/whoami").mock(
        return_value=httpx.Response(200, json={"sub": "user-1"})
    )
    result = runner.invoke(app, ["auth", "whoami"])
    assert result.exit_code == 0, result.output
    assert route.called
    assert "user-1" in result.output


@respx.mock
def test_config_get_calls_effective(monkeypatch) -> None:
    monkeypatch.setenv("AQP_ACCESS_TOKEN", "tok_test_123")
    route = respx.get("http://localhost:8000/configs/effective").mock(
        return_value=httpx.Response(200, json={"deep_model": "gpt-5.5"})
    )
    result = runner.invoke(app, ["config", "get", "llm"])
    assert result.exit_code == 0, result.output
    assert route.called
    assert "gpt-5.5" in result.output


@respx.mock
def test_cp_deployments_list_calls_control_plane(monkeypatch) -> None:
    monkeypatch.setenv("AQP_ACCESS_TOKEN", "tok_test_123")
    route = respx.get("http://localhost:9000/manage/deployments").mock(
        return_value=httpx.Response(200, json=[{"service_id": "api", "status": "running"}])
    )
    result = runner.invoke(app, ["cp", "deployments", "list"])
    assert result.exit_code == 0, result.output
    assert route.called
    assert "api" in result.output


@respx.mock
def test_deploy_plan_selects_workspace_and_plans(monkeypatch) -> None:
    monkeypatch.setenv("AQP_ACCESS_TOKEN", "tok_test_123")
    workspaces = respx.get("http://localhost:8000/terraform/workspaces").mock(
        return_value=httpx.Response(200, json=[{"id": "ws-local", "slug": "local-default"}])
    )
    plan = respx.post("http://localhost:8000/terraform/workspaces/ws-local/plan").mock(
        return_value=httpx.Response(
            200,
            json={
                "task_id": "task-123",
                "status": "queued",
                "stream_url": "/ws/terraform/runs/run-123",
            },
        )
    )
    result = runner.invoke(app, ["deploy", "plan"])
    assert result.exit_code == 0, result.output
    assert workspaces.called
    assert plan.called
    assert "run-123" in result.output


def test_tools_bots_wrapper_reports_missing_binary(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    result = runner.invoke(app, ["tools", "bots", "status"])
    assert result.exit_code == 127
    assert "not found on PATH" in result.output
