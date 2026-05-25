"""Regression tests for ``scripts/ci/check_migration_chain.py``."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_migration_chain")
    versions_dir = tmp_path / "alembic" / "versions"
    versions_dir.mkdir(parents=True)
    monkeypatch.setattr(module, "VERSIONS_DIR", versions_dir, raising=True)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _write(path: Path, revision: str, down: str | None | tuple[str, ...]) -> None:
    if down is None:
        down_repr = "None"
    elif isinstance(down, tuple):
        inner = ", ".join(repr(d) for d in down)
        down_repr = f"({inner})"
    else:
        down_repr = repr(down)
    path.write_text(
        f"revision = {revision!r}\ndown_revision = {down_repr}\n",
        encoding="utf-8",
    )


def test_linear_chain_passes(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001.py", "0001", None)
    _write(versions / "0002.py", "0002", "0001")
    _write(versions / "0003.py", "0003", "0002")
    assert lint_module.check_chain() == []


def test_merge_revision_passes(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001.py", "0001", None)
    _write(versions / "0002a.py", "0002a", "0001")
    _write(versions / "0002b.py", "0002b", "0001")
    _write(versions / "0003_merge.py", "0003", ("0002a", "0002b"))
    assert lint_module.check_chain() == []


def test_two_heads_fails(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001.py", "0001", None)
    _write(versions / "0002a.py", "0002a", "0001")
    _write(versions / "0002b.py", "0002b", "0001")
    errors = lint_module.check_chain()
    assert any("multiple heads" in err for err in errors)


def test_orphan_parent_fails(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001.py", "0001", None)
    _write(versions / "0002.py", "0002", "missing_parent")
    errors = lint_module.check_chain()
    assert any("missing_parent" in err for err in errors)


def test_duplicate_revision_fails(lint_module) -> None:
    versions = lint_module.VERSIONS_DIR
    _write(versions / "0001a.py", "0001", None)
    _write(versions / "0001b.py", "0001", None)
    with pytest.raises(SystemExit):
        lint_module.check_chain()


def test_real_chain_passes_when_run_against_repo(monkeypatch, load_lint_script) -> None:
    """Sanity: the real `alembic/versions/` graph in this repo is valid."""
    module = load_lint_script("check_migration_chain")
    errors = module.check_chain()
    assert errors == [], "real alembic chain has errors: " + "\n".join(errors)
