"""Regression tests for ``scripts/ci/check_migration_immutability.py``."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    """Load the lint with its module-level paths repointed at ``tmp_path``."""
    module = load_lint_script("check_migration_immutability")

    versions_dir = tmp_path / "alembic" / "versions"
    versions_dir.mkdir(parents=True)
    monkeypatch.setattr(module, "VERSIONS_DIR", versions_dir, raising=True)
    monkeypatch.setattr(module, "LOCK_PATH", versions_dir / ".hashes.lock", raising=True)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_clean_state_passes(lint_module, capsys) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001_initial.py", "revision = '0001'\n")
    _write(versions / "0002_next.py", "revision = '0002'\n")

    rc = lint_module.cmd_update()
    assert rc == 0
    payload = json.loads(lint_module.LOCK_PATH.read_text())
    assert set(payload) == {"0001_initial.py", "0002_next.py"}

    rc = lint_module.cmd_check(strict_new=False)
    assert rc == 0
    captured = capsys.readouterr()
    assert "OK" in captured.out


def test_drift_on_locked_migration_fails(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001_initial.py", "revision = '0001'\n# original\n")
    lint_module.cmd_update()

    # Mutate after locking.
    _write(versions / "0001_initial.py", "revision = '0001'\n# tampered\n")
    rc = lint_module.cmd_check(strict_new=False)
    assert rc == 1


def test_new_unlocked_migration_passes_in_default_mode(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001_initial.py", "revision = '0001'\n")
    lint_module.cmd_update()

    _write(versions / "0002_added_after_lock.py", "revision = '0002'\n")
    assert lint_module.cmd_check(strict_new=False) == 0
    assert lint_module.cmd_check(strict_new=True) == 1


def test_missing_locked_migration_fails(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    f = versions / "0001_initial.py"
    _write(f, "revision = '0001'\n")
    lint_module.cmd_update()
    f.unlink()
    assert lint_module.cmd_check(strict_new=False) == 1


def test_no_lock_file_warns_but_passes(lint_module, capsys) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001_initial.py", "revision = '0001'\n")
    rc = lint_module.cmd_check(strict_new=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "no lock file" in out
