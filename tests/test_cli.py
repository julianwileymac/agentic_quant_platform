"""Smoke tests for the ``aqp`` CLI."""
from __future__ import annotations

from typer.testing import CliRunner

from aqp.cli.main import app

runner = CliRunner()


def test_aqp_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "paper" in result.stdout.lower()
    assert "backtest" in result.stdout.lower()
    assert "data" in result.stdout.lower()


def test_aqp_paper_help() -> None:
    result = runner.invoke(app, ["paper", "--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout.lower()
    assert "stop" in result.stdout.lower()


def test_aqp_data_help() -> None:
    result = runner.invoke(app, ["data", "--help"])
    assert result.exit_code == 0
    assert "load" in result.stdout.lower()
    assert "ingest" in result.stdout.lower()


def test_aqp_backtest_help() -> None:
    result = runner.invoke(app, ["backtest", "--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout.lower()


def test_aqp_dash_mounted_prints_url() -> None:
    """``aqp dash`` (default --mounted) should not crash when API isn't running."""
    result = runner.invoke(app, ["dash", "--mounted"])
    assert result.exit_code == 0
    assert "/dash/" in result.stdout
