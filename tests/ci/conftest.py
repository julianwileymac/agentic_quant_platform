"""Common fixtures for the Phase 0 lint regression tests."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_CI = REPO_ROOT / "scripts" / "ci"


@pytest.fixture(autouse=True)
def _ensure_scripts_ci_on_path() -> None:
    """Make the lint scripts importable as plain modules.

    Each lint script lives at ``scripts/ci/check_*.py`` and is imported
    by the regression tests via ``importlib`` so we exercise their
    ``main()`` entry points directly. Adding the dir to ``sys.path``
    means the helper imports (``from _lint_allowlist import ...``) work
    transparently.
    """
    path_str = str(SCRIPTS_CI)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _load_script(stem: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"aqp_ci_{stem}", SCRIPTS_CI / f"{stem}.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {stem}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def load_lint_script():
    """Factory: ``module = load_lint_script("check_credential_resolver")``."""
    return _load_script


@pytest.fixture(autouse=True)
def _isolate_allowlist_repo_root(monkeypatch, tmp_path) -> None:
    """Redirect the shared allowlist module's REPO_ROOT to ``tmp_path``.

    Without this, regression tests that synthesise tiny ``.py`` files
    under ``tmp_path`` and assert they trigger a lint violation can be
    silently dropped when the violation path coincides with an entry
    already on the real allowlist (e.g. ``aqp/trading/brokerages/alpaca.py``
    is on the Rule 55 allowlist). Pointing ``_lint_allowlist.REPO_ROOT``
    at ``tmp_path`` guarantees the path-relative lookup never matches a
    real entry. The empty allowlist directory under ``tmp_path`` means
    every violation flows through.
    """
    import _lint_allowlist  # type: ignore[import-not-found]

    monkeypatch.setattr(_lint_allowlist, "REPO_ROOT", tmp_path, raising=True)
    # Point the allowlist directory at an empty subdir so no real
    # allowlist files leak through.
    empty_allowlists = tmp_path / "_test_allowlists"
    empty_allowlists.mkdir(exist_ok=True)
    monkeypatch.setattr(
        _lint_allowlist, "ALLOWLIST_DIR", empty_allowlists, raising=True
    )
