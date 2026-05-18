"""Tests for :class:`aqp.terraform.runner.TerraformExecutor`."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from aqp.terraform.runner import TerraformExecutor, TerraformExecutorResult
from aqp.terraform.spec import TerraformStackSpec


def _spec() -> TerraformStackSpec:
    return TerraformStackSpec(
        name="aqp-local",
        slug="aqp-local",
        module_kind="composite",
        environment="local",
        cloud_provider="local",
    )


def _result(*, exit_code: int, stderr_log_path: Path, error: str | None = None) -> TerraformExecutorResult:
    return TerraformExecutorResult(
        action="init",
        workspace_dir=str(stderr_log_path.parent),
        exit_code=exit_code,
        duration_ms=1.0,
        stdout_log_path=str(stderr_log_path.parent / "init.stdout.log"),
        stderr_log_path=str(stderr_log_path),
        error=error,
    )


def test_env_sets_cli_config_file_when_present(tmp_path, monkeypatch):
    from aqp.config import settings

    cli_config = tmp_path / "terraform.tfrc"
    cli_config.write_text("# test", encoding="utf-8")
    cache_dir = tmp_path / "plugin-cache"

    monkeypatch.setattr(
        settings, "terraform_cli_config_file", str(cli_config), raising=True
    )

    executor = TerraformExecutor(
        workspace_slug="aqp-local",
        spec=_spec(),
        plugin_cache_dir=str(cache_dir),
    )

    env = executor._env()
    assert env["TF_CLI_CONFIG_FILE"] == str(cli_config)
    assert env["TF_PLUGIN_CACHE_DIR"] == str(cache_dir)


def test_init_retries_transient_failures(tmp_path, monkeypatch):
    stderr_1 = tmp_path / "init-1.stderr.log"
    stderr_1.write_text("Failed to install provider", encoding="utf-8")
    stderr_2 = tmp_path / "init-2.stderr.log"
    stderr_2.write_text("", encoding="utf-8")

    first = _result(exit_code=1, stderr_log_path=stderr_1)
    second = _result(exit_code=0, stderr_log_path=stderr_2)

    executor = TerraformExecutor(workspace_slug="aqp-local", spec=_spec())

    calls: list[TerraformExecutorResult] = [first, second]
    monkeypatch.setattr(
        executor,
        "_run",
        lambda *args, **kwargs: calls.pop(0),
    )
    monkeypatch.setattr(executor, "_init_retry_attempts", lambda: 3)
    monkeypatch.setattr(executor, "_init_retry_sleep_seconds", lambda attempt: 0.0)

    result = executor.init()
    assert result.exit_code == 0
    assert executor._initialised is True
    assert calls == []


def test_init_does_not_retry_non_transient_failures(tmp_path, monkeypatch):
    stderr = tmp_path / "init.stderr.log"
    stderr.write_text("Error: Invalid block definition", encoding="utf-8")
    failed = _result(exit_code=1, stderr_log_path=stderr)

    executor = TerraformExecutor(workspace_slug="aqp-local", spec=_spec())
    run_calls: list[int] = []

    def _fake_run(*_args, **_kwargs):
        run_calls.append(1)
        return failed

    monkeypatch.setattr(executor, "_run", _fake_run)
    monkeypatch.setattr(executor, "_init_retry_attempts", lambda: 5)

    result = executor.init()
    assert result.exit_code == 1
    assert len(run_calls) == 1
    assert "terraform init failed" in (result.error or "")


def test_outputs_json_uses_executor_environment(tmp_path, monkeypatch):
    wd = tmp_path / "workspace"
    wd.mkdir()
    executor = TerraformExecutor(
        workspace_slug="aqp-local",
        spec=_spec(),
        prerendered_workspace_dir=str(wd),
        env_overrides={"TF_VAR_namespace": "aqp-local"},
    )

    captured: dict[str, object] = {}

    def _fake_run(args, *, cwd, env, check, capture_output, timeout):
        captured["args"] = args
        captured["cwd"] = cwd
        captured["env"] = env
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["timeout"] = timeout
        return SimpleNamespace(
            returncode=0,
            stdout=b'{"namespace":{"value":"aqp-local"},"ignored":"raw"}',
        )

    monkeypatch.setattr("aqp.terraform.runner.subprocess.run", _fake_run)

    outputs = executor.outputs_json()
    assert outputs == {"namespace": "aqp-local"}
    assert captured["args"] == [executor._binary_path(), "output", "-json"]
    assert captured["cwd"] == str(wd)
    assert captured["env"]["TF_VAR_namespace"] == "aqp-local"

