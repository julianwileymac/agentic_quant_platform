"""Legacy `aqp deploy` compatibility-shim tests."""
from __future__ import annotations

import pytest


def test_deploy_wrapper_forwards_args(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_forward(argv: list[str]) -> int:
        called["argv"] = argv
        return 0

    monkeypatch.setattr("aqp.cli.deploy_cmd.run_aqp_cli", _fake_forward)
    from aqp.cli.deploy_cmd import main

    result = main(["up", "--workspace-id", "local-ws"])
    assert result == 0
    assert called["argv"] == ["deploy", "up", "--workspace-id", "local-ws"]


def test_deploy_wrapper_exit_code_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aqp.cli.deploy_cmd.run_aqp_cli", lambda argv: 19)
    from aqp.cli.deploy_cmd import main

    result = main(["plan"])
    assert result == 19


def test_deploy_app_registered_on_main():
    from aqp.cli.main import app

    # The command tree should expose 'deploy' as a subcommand.
    cmds = {c.name for c in getattr(app, "registered_groups", [])}
    assert "deploy" in cmds
