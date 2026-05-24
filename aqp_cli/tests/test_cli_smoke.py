"""Smoke tests for the top-level CLI surface."""
from __future__ import annotations

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
    for group in ("setup", "services", "update", "auth"):
        assert group in result.stdout


def test_auth_direct_requires_understanding() -> None:
    """--direct without --i-understand exits non-zero per rule 27."""
    result = runner.invoke(app, ["auth", "login", "--direct"])
    assert result.exit_code != 0
