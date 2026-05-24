"""Smoke tests for legacy `aqp` compatibility shims."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from aqp.cli.main import app, main

runner = CliRunner()


def test_aqp_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout.lower()
    assert "config" in out
    assert "cp" in out
    assert "deploy" in out
    assert "viz" in out


def test_aqp_forwards_unknown_top_level_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_forward(argv: list[str]) -> int:
        called["argv"] = argv
        return 0

    monkeypatch.setattr("aqp.cli.main.run_aqp_cli", _fake_forward)
    monkeypatch.setattr("sys.argv", ["aqp", "paper", "run", "--symbol", "AAPL"])
    result = main()
    assert result == 0
    assert called["argv"] == ["paper", "run", "--symbol", "AAPL"]


def test_aqp_deploy_subcommand_forwards(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_forward(argv: list[str]) -> int:
        called["argv"] = argv
        return 0

    monkeypatch.setattr("aqp.cli.main.run_aqp_cli", _fake_forward)
    monkeypatch.setattr("sys.argv", ["aqp", "deploy", "up", "--workspace-id", "ws1"])
    result = main()
    assert result == 0
    assert called["argv"] == ["deploy", "up", "--workspace-id", "ws1"]
