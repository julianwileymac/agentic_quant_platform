"""Regression tests for ``scripts/ci/check_credential_resolver.py``."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_credential_resolver")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    # Constrain the scan roots to our temp tree's `aqp/`.
    monkeypatch.setattr(module, "SCAN_ROOTS", ("aqp",), raising=True)
    return module


def _make_file(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_direct_settings_token_read_fails(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import settings\n"
        "\n"
        "def fetch():\n"
        "    return settings.datahub_token\n"
    )
    _make_file(tmp_path, "aqp/api/routes/foo.py", body)
    rc = lint_module.main([])
    assert rc == 1


def test_aliased_module_read_fails(lint_module, tmp_path) -> None:
    body = (
        "import aqp.config as cfg\n"
        "\n"
        "def fetch():\n"
        "    return cfg.settings.foo_secret\n"
    )
    _make_file(tmp_path, "aqp/api/routes/bar.py", body)
    assert lint_module.main([]) == 1


def test_exempt_directory_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import settings\n"
        "\n"
        "def fetch():\n"
        "    return settings.datahub_token\n"
    )
    # `aqp/credentials/...` is in EXEMPT_PREFIXES.
    _make_file(tmp_path, "aqp/credentials/stores/foo.py", body)
    assert lint_module.main([]) == 0


def test_clean_file_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.credentials.resolver import get_resolver\n"
        "from aqp.credentials.protocol import CredentialKey\n"
        "\n"
        "def fetch() -> str:\n"
        "    return get_resolver().resolve(\n"
        "        CredentialKey('datahub', 'token'), required=True\n"
        "    ).require('token')\n"
    )
    _make_file(tmp_path, "aqp/api/routes/clean.py", body)
    assert lint_module.main([]) == 0


def test_non_credential_attr_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import settings\n"
        "\n"
        "def fetch():\n"
        "    return settings.datahub_gms_url\n"
    )
    _make_file(tmp_path, "aqp/api/routes/url.py", body)
    assert lint_module.main([]) == 0
